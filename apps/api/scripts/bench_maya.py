"""End-to-end Maya benchmark — times every tool call, model call, and sub-agent.

Runs ONE founder turn through the real coordinator (real Vertex + firecrawl +
Supabase), with a callback handler that records wall-time for every LLM call and
every tool call (correlated by run_id). Prints a breakdown so we can see exactly
where the seconds go, and dumps the research queries + sources so we can verify
the specialists ground in Reddit / app-store / community sources.

Usage:
    python scripts/bench_maya.py <project_id> "<founder message>"

Note: tool/model durations OVERLAP (specialists run in parallel), so the sum of
durations exceeds wall-clock. Both are reported — sum = total work, wall = elapsed.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage

from app.config import settings
# firecrawl.py reads os.getenv("FIRECRAWL_API_KEY"); pydantic-settings does NOT
# push .env values to os.environ (prod sets it as a real Cloud Run env var). For
# a faithful LOCAL run, forward it ourselves so the specialists actually hit the web.
if settings.firecrawl_api_key:
    os.environ.setdefault("FIRECRAWL_API_KEY", settings.firecrawl_api_key)

from app.deepagent.coordinator import build_maya
from app.deepagent.domain_tools import set_active_project


class Timing(BaseCallbackHandler):
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._open: dict = {}

    # ── LLM / chat-model calls ──
    def _open_model(self, run_id, metadata, invocation_params, serialized):
        model = None
        if metadata:
            model = metadata.get("ls_model_name")
        if not model and invocation_params:
            model = invocation_params.get("model") or invocation_params.get("model_name")
        if not model and serialized:
            model = (serialized.get("kwargs") or {}).get("model")
        self._open[run_id] = ("model", model or "model", time.perf_counter(), {})

    def on_chat_model_start(self, serialized, messages, *, run_id, metadata=None,
                            invocation_params=None, **kw):
        self._open_model(run_id, metadata, invocation_params, serialized)

    def on_llm_start(self, serialized, prompts, *, run_id, metadata=None,
                     invocation_params=None, **kw):
        if run_id not in self._open:
            self._open_model(run_id, metadata, invocation_params, serialized)

    def on_llm_end(self, response, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if not rec:
            return
        _, name, start, _ = rec
        toks = {}
        try:
            msg = response.generations[0][0].message
            toks = getattr(msg, "usage_metadata", None) or {}
        except Exception:
            pass
        self.events.append({"kind": "model", "name": name,
                            "dur": time.perf_counter() - start, "tokens": toks})

    def on_llm_error(self, error, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if rec:
            self.events.append({"kind": "model", "name": rec[1],
                                "dur": time.perf_counter() - rec[2], "error": str(error)[:200]})

    # ── tool calls ──
    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **kw):
        name = (serialized or {}).get("name") or "tool"
        args = inputs or {}
        sub = args.get("subagent_type") or args.get("subagent") if name == "task" else None
        q = args.get("query") or args.get("url") or args.get("description") or ""
        self._open[run_id] = ("tool", name, time.perf_counter(), {"sub": sub, "q": str(q)[:200]})

    def on_tool_end(self, output, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if not rec:
            return
        _, name, start, extra = rec
        out = output if isinstance(output, str) else getattr(output, "content", str(output))
        self.events.append({"kind": "tool", "name": name, "dur": time.perf_counter() - start,
                            "sub": extra["sub"], "q": extra["q"], "out": str(out)[:6000]})

    def on_tool_error(self, error, *, run_id, **kw):
        rec = self._open.pop(run_id, None)
        if rec:
            self.events.append({"kind": "tool", "name": rec[1], "dur": time.perf_counter() - rec[2],
                                "sub": rec[3].get("sub"), "q": rec[3].get("q"), "error": str(error)[:200]})


async def main() -> None:
    pid = sys.argv[1]
    msg = sys.argv[2]
    set_active_project(pid)
    agent = build_maya(checkpointer=None)
    cb = Timing()

    print(f"\n=== RUN === project={pid}\nmessage: {msg}\n")
    t0 = time.perf_counter()
    status = "ok"
    try:
        await asyncio.wait_for(
            agent.ainvoke({"messages": [HumanMessage(content=msg)]},
                          config={"recursion_limit": 45, "callbacks": [cb]}),
            timeout=420,
        )
    except Exception as e:  # GraphRecursionError, timeout, etc.
        status = f"{type(e).__name__}: {str(e)[:160]}"
    wall = time.perf_counter() - t0

    ev = cb.events
    models = [e for e in ev if e["kind"] == "model"]
    tools = [e for e in ev if e["kind"] == "tool"]
    model_sum = sum(e["dur"] for e in models)
    tool_sum = sum(e["dur"] for e in tools)

    print(f"\n========== BENCHMARK ==========\nstatus: {status}")
    print(f"WALL (elapsed): {wall:6.1f}s")
    print(f"model calls: {len(models):3}  total {model_sum:6.1f}s (overlaps; parallel)")
    print(f"tool  calls: {len(tools):3}  total {tool_sum:6.1f}s (overlaps; parallel)")

    print("\n--- model time by model ---")
    by_model = defaultdict(lambda: [0, 0.0, 0])  # count, dur, thinking_tokens
    for e in models:
        b = by_model[e["name"]]
        b[0] += 1
        b[1] += e["dur"]
        tk = e.get("tokens") or {}
        b[2] += (tk.get("output_token_details", {}) or {}).get("reasoning", 0) if isinstance(tk, dict) else 0
    for name, (c, d, think) in sorted(by_model.items(), key=lambda x: -x[1][1]):
        print(f"  {name:28} calls {c:3}  {d:6.1f}s  avg {d/c:4.1f}s  thinkTok {think}")

    print("\n--- tool time by tool ---")
    by_tool = defaultdict(lambda: [0, 0.0])
    for e in tools:
        b = by_tool[e["name"]]
        b[0] += 1
        b[1] += e["dur"]
    for name, (c, d) in sorted(by_tool.items(), key=lambda x: -x[1][1]):
        print(f"  {name:18} calls {c:3}  {d:6.1f}s  avg {d/c:4.1f}s")

    print("\n--- sub-agent dispatches (task) ---")
    for e in tools:
        if e["name"] == "task":
            print(f"  {str(e['sub']):8} {e['dur']:6.1f}s  brief: {e['q'][:80]}")

    print("\n--- research queries (web_search / reddit_research / crawl_website) ---")
    for e in tools:
        if e["name"] in ("web_search", "reddit_research", "crawl_website"):
            print(f"  [{e['dur']:5.1f}s] {e['name']}: {e['q'][:110]}")

    # Grounding check: the task output is a deepagents Command(...) wrapping a
    # ToolMessage whose content is the SpecialistResult JSON — so we regex the
    # `sources` array out of the raw (escaped) string rather than json.loads it.
    import re
    print("\n--- specialist sources (grounding check) ---")
    for e in tools:
        if e["name"] == "task" and e.get("out"):
            m = re.search(r'\\+"sources\\+":(\[[^\]]*\])', e["out"])
            srcs = []
            if m:
                try:
                    srcs = json.loads(m.group(1).replace('\\"', '"').replace('\\\\', '\\'))
                except Exception:
                    pass
            print(f"  {e['sub']}: {len(srcs)} sources")
            for s in srcs:
                print(f"     {s}")

    # Persist raw events for deeper analysis.
    with open("bench_events.json", "w", encoding="utf-8") as f:
        json.dump({"wall": wall, "status": status, "events": ev}, f, indent=2, default=str)
    print("\n(raw events -> apps/api/bench_events.json)")


if __name__ == "__main__":
    asyncio.run(main())
