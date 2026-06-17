"""A/B benchmark: Maya on gemini-3.5-flash vs gemini-3.1-pro-preview.

Runs the SAME founder scenario N times per model (specialists are identical flash
tiers in both — only Maya's orchestrator model varies), on fresh throwaway
projects it creates + deletes itself. Captures speed (wall), work (tokens via
callback), behavior (specialists dispatched, searches, sources cited, premature
creations), and — crucially — Maya's full final synthesis text so quality can be
judged afterward. Cost is read authoritatively from LangSmith per trace.

Usage:  python scripts/bench_compare.py [reps]
Writes incrementally to apps/api/bench_compare.json (survives a mid-crash).
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from collections import defaultdict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings

if settings.firecrawl_api_key:
    os.environ.setdefault("FIRECRAWL_API_KEY", settings.firecrawl_api_key)

from app.db import require_admin
from app.deepagent.coordinator import build_maya
from app.deepagent.domain_tools import set_active_project

USER_ID = "fca4c898-3a43-4351-855c-10e7fe63d377"
MODELS = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
SCENARIO = (
    "I built an app that analyzes live political debates in real time — it transcribes, "
    "fact-checks claims, and auto-clips the key moments. I launched it a month ago but "
    "almost nobody is using it. Did I build for the wrong audience? Who actually wants "
    "this and where would I find them?"
)
CREATE_TOOLS = {"create_artifact", "create_solution", "create_feature", "write_prd", "create_sprint"}
SEARCH_TOOLS = {"web_search", "reddit_research", "crawl_website"}
OUT = "bench_compare.json"


class Timing(BaseCallbackHandler):
    def __init__(self):
        self.events = []
        self._open = {}

    def _om(self, run_id, metadata, ip, serialized):
        m = (metadata or {}).get("ls_model_name") or (ip or {}).get("model") \
            or ((serialized or {}).get("kwargs") or {}).get("model")
        self._open[run_id] = ("model", m or "model", time.perf_counter())

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None, invocation_params=None, **kw):
        self._om(run_id, metadata, invocation_params, serialized)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None, invocation_params=None, **kw):
        if run_id not in self._open:
            self._om(run_id, metadata, invocation_params, serialized)

    def on_llm_end(self, response, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if not rec:
            return
        toks = {}
        try:
            toks = getattr(response.generations[0][0].message, "usage_metadata", None) or {}
        except Exception:
            pass
        self.events.append({"kind": "model", "name": rec[1], "dur": time.perf_counter() - rec[2], "tokens": toks})

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kw):
        name = (serialized or {}).get("name") or "tool"
        args = inputs or {}
        self._open[run_id] = ("tool", name, time.perf_counter(),
                              args.get("subagent_type") if name == "task" else None)

    def on_tool_end(self, output, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if not rec:
            return
        out = output if isinstance(output, str) else getattr(output, "content", str(output))
        self.events.append({"kind": "tool", "name": rec[1], "dur": time.perf_counter() - rec[2],
                            "sub": rec[3], "out": str(out)[:8000]})

    def on_tool_error(self, error, *, run_id, **kw):
        self._open.pop(run_id, None)


def new_project(tag):
    r = require_admin().table("projects").insert(
        {"user_id": USER_ID, "name": f"BENCHAB-{tag}", "entry_type": "fresh_idea"}).execute()
    return r.data[0]["id"]


def del_project(pid):
    try:
        require_admin().table("projects").delete().eq("id", pid).execute()
    except Exception:
        pass


def count_sources(events):
    import re
    n = 0
    raw = json.dumps([e.get("out", "") for e in events if e["name"] == "task"])
    for m in re.finditer(r'sources\\+":(\[[^\]]*\])', raw):
        try:
            n += len(json.loads(m.group(1).replace('\\"', '"').replace('\\\\', '\\')))
        except Exception:
            pass
    return n


async def run_once(model, rep):
    pid = new_project(f"{model.split('-')[1]}-{rep}-{int(time.time())}")
    set_active_project(pid)
    settings.maya_model = model
    cb = Timing()
    started = time.time()
    t0 = time.perf_counter()
    status, maya_texts = "ok", []
    try:
        agent = build_maya(checkpointer=None)
        res = await asyncio.wait_for(
            agent.ainvoke({"messages": [HumanMessage(content=SCENARIO)]},
                          config={"recursion_limit": 45, "callbacks": [cb]}), timeout=450)
        for m in res.get("messages", []):
            if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip():
                maya_texts.append(m.content.strip())
    except Exception as e:
        status = f"{type(e).__name__}: {str(e)[:150]}"
    wall = time.perf_counter() - t0
    del_project(pid)

    models = [e for e in cb.events if e["kind"] == "model"]
    tools = [e for e in cb.events if e["kind"] == "tool"]
    tok = defaultdict(int)
    by_model = defaultdict(lambda: [0, 0, 0, 0])
    for e in models:
        t = e.get("tokens") or {}
        tok["in"] += t.get("input_tokens", 0)
        tok["out"] += t.get("output_tokens", 0)
        tok["think"] += (t.get("output_token_details", {}) or {}).get("reasoning", 0)
        b = by_model[e["name"]]
        b[0] += 1
        b[1] += t.get("input_tokens", 0)
        b[2] += t.get("output_tokens", 0)
        b[3] += (t.get("output_token_details", {}) or {}).get("reasoning", 0)
    return {
        "model": model, "rep": rep, "started": started, "wall": round(wall, 1), "status": status,
        "model_time": round(sum(e["dur"] for e in models), 1),
        "tool_time": round(sum(e["dur"] for e in tools), 1),
        "model_calls": len(models),
        "n_task": sum(1 for e in tools if e["name"] == "task"),
        "dispatched": [e["sub"] for e in tools if e["name"] == "task"],
        "n_search": sum(1 for e in tools if e["name"] in SEARCH_TOOLS),
        "n_create": sum(1 for e in tools if e["name"] in CREATE_TOOLS),
        "n_sources": count_sources(tools),
        "tokens": dict(tok), "by_model": {k: v for k, v in by_model.items()},
        "maya_msgs": len(maya_texts), "final": maya_texts[-1] if maya_texts else "",
        "maya_texts": maya_texts,
    }


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results = []
    for model in MODELS:
        for rep in range(reps):
            print(f"\n>>> {model} rep{rep} ...", flush=True)
            r = await run_once(model, rep)
            print(f"    wall={r['wall']}s status={r['status']} dispatched={r['dispatched']} "
                  f"searches={r['n_search']} sources={r['n_sources']} creates={r['n_create']} "
                  f"mayaMsgs={r['maya_msgs']} tokens(in/out/think)={r['tokens']}", flush=True)
            results.append(r)
            json.dump(results, open(OUT, "w", encoding="utf-8"), indent=2, default=str)

    print("\n==================== AGGREGATE ====================", flush=True)
    for model in MODELS:
        ok = [r for r in results if r["model"] == model and r["status"] == "ok"]
        if not ok:
            print(f"\n{model}: NO successful runs")
            continue
        def mean(k): return statistics.mean([r[k] for r in ok])
        def rng(k): return f"{min(r[k] for r in ok):.0f}-{max(r[k] for r in ok):.0f}"
        print(f"\n{model}  (n={len(ok)}/{reps})")
        print(f"  wall      mean {mean('wall'):6.1f}s   range {rng('wall')}")
        print(f"  modelcalls mean {mean('model_calls'):4.1f}     tasks {mean('n_task'):.1f}  searches {mean('n_search'):.1f}")
        print(f"  sources   mean {mean('n_sources'):4.1f}     creates {mean('n_create'):.1f}  mayaMsgs {mean('maya_msgs'):.1f}")
        tin = statistics.mean([r['tokens'].get('in', 0) for r in ok])
        tout = statistics.mean([r['tokens'].get('out', 0) for r in ok])
        tthink = statistics.mean([r['tokens'].get('think', 0) for r in ok])
        print(f"  tokens    in {tin:.0f}  out {tout:.0f}  thinking {tthink:.0f}  (all models; cost via LangSmith)")
    print(f"\n(full results incl. Maya syntheses -> apps/api/{OUT})", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
