"""Cost / token comparison harness for Maya model swaps.

Runs the same prompt through Maya's LLM (whatever's configured) and reports:
  - prompt tokens
  - completion tokens
  - cached tokens (implicit Gemini cache hit if any)
  - estimated USD cost
  - wall time

Call twice — once before a config change, once after — and diff.

Usage:
    cd apps/api
    set PYTHONIOENCODING=utf-8 & set PYTHONUNBUFFERED=1
    python -u -X utf8 -m tests.cost_compare [LABEL]

LABEL is just a string printed in the report so you can tell runs apart.
Defaults to the current `settings.maya_model`.

This intentionally bypasses the full Maya graph — the goal is to measure
the COST per LLM call, not the whole orchestration overhead. The system
prompt + state block + a synthetic conversation are sent to the same model
Maya would use, twice (to verify caching kicks in on the second call).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402  (also forwards env vars)
from app.services import prompts  # noqa: E402
from langchain.chat_models import init_chat_model  # noqa: E402
from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402


# Pricing (per million tokens) — keep up to date with Google Cloud pricing.
# https://cloud.google.com/vertex-ai/generative-ai/pricing
PRICING = {
    # Real pricing from https://ai.google.dev/gemini-api/docs/pricing
    # Confirmed 2026-05-25.
    "gemini-3.5-flash":          {"input": 1.50,  "cached": 0.15,  "output": 9.00},
    "gemini-3.1-pro-preview":    {"input": 2.00,  "cached": 0.50,  "output": 12.00},  # <200K tokens
    "gemini-3-flash-preview":    {"input": 0.50,  "cached": 0.125, "output": 3.00},
    "gemini-3.1-flash-lite":     {"input": 0.25,  "cached": 0.025, "output": 1.50},
}


def _estimate_cost(model_name: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int) -> float:
    """USD cost estimate. Returns 0.0 if we don't have pricing for the model."""
    p = PRICING.get(model_name)
    if not p:
        return 0.0
    uncached_input = max(0, prompt_tokens - cached_tokens)
    return (
        (uncached_input * p["input"]
         + cached_tokens * p["cached"]
         + completion_tokens * p["output"]) / 1_000_000
    )


def _pull_usage(response) -> dict:
    """Extract token counts from a LangChain AIMessage response. Handles the
    two shapes Vertex returns (usage_metadata dict vs LangChain UsageMetadata)."""
    out = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0, "thoughts_tokens": 0}
    # LangChain-native usage_metadata (preferred)
    um = getattr(response, "usage_metadata", None)
    if isinstance(um, dict):
        out["prompt_tokens"]     = um.get("input_tokens", 0) or 0
        out["completion_tokens"] = um.get("output_tokens", 0) or 0
        details = um.get("input_token_details") or {}
        out["cached_tokens"] = details.get("cache_read", 0) or details.get("cached", 0) or 0
        od = um.get("output_token_details") or {}
        out["thoughts_tokens"] = od.get("reasoning", 0) or 0
    # Raw vertex response shape — fall through if usage_metadata above was thin
    raw = getattr(response, "response_metadata", None) or {}
    raw_um = raw.get("usage_metadata") if isinstance(raw, dict) else None
    if isinstance(raw_um, dict):
        if not out["prompt_tokens"]:
            out["prompt_tokens"] = raw_um.get("prompt_token_count", 0) or 0
        if not out["completion_tokens"]:
            out["completion_tokens"] = raw_um.get("candidates_token_count", 0) or 0
        if not out["cached_tokens"]:
            out["cached_tokens"] = raw_um.get("cached_content_token_count", 0) or 0
        if not out["thoughts_tokens"]:
            out["thoughts_tokens"] = raw_um.get("thoughts_token_count", 0) or 0
    return out


def _synthetic_state_block() -> str:
    """Stand-in for a realistic state block — ~2-3KB of fake decisions /
    artifacts to approximate what an active project would include."""
    return (
        "\n\n# Project state — read this carefully before any action this turn\n\n"
        "## Discovery flow (12 stages — RECOMMENDED order, not rigid)\n"
        "- Stage 1 (Problem framing) ✓ COMPLETE — Working parents struggle to find dietitian-approved alarm experiences\n"
        "- Stage 2 (People + competitive) ✓ COMPLETE — Target user: ADHD adults age 25-40 who oversleep on weekday mornings\n"
        "- Stage 3 (Tech feasibility) ✓ COMPLETE — Android-only MVP, Vertex AI for voice synthesis, Firebase auth\n"
        "- Stage 4 (Friction + failure) ✓ COMPLETE — Top friction: app gets killed by Android battery optimizer\n"
        "- Stage 5 (User stories) → in progress — drafting now\n"
        "- Stage 6 (Screens) ·\n"
        "- Stage 7 (Dev environment) ·\n"
        "- Stage 8 (Spec lock) ·\n\n"
        "## Active decisions\n"
        "- **D-001** [scope] Android-only for MVP — iOS is post-launch\n"
        "- **D-002** [tech] Vertex AI for voice synthesis; cache audio overnight\n"
        "- **D-003** [auth] Firebase auth, email + Google\n"
        "- **D-004** [scope] No social features in MVP — single-user only\n\n"
        "## Active discovery artifacts\n"
        "- `01234567-89ab-cdef-0123-456789abcdef` [problem_statement] {stage: problem_framing}\n"
        "- `12345678-9abc-def0-1234-56789abcdef0` [positioning_summary] {stage: people_competitive}\n"
        "- `23456789-abcd-ef01-2345-6789abcdef01` [tech_constraints] {stage: tech_feasibility}\n"
        "- `3456789a-bcde-f012-3456-789abcdef012` [friction_summary] {stage: friction_failure}\n"
        "- `456789ab-cdef-0123-4567-89abcdef0123` [persona_cards] {stage: people_competitive}\n\n"
    )


def _synthetic_messages():
    """A handful of fake prior messages so the input is realistically sized."""
    return [
        HumanMessage(content="I want to build an alarm app for ADHD adults that uses 2-way voice AI to gently wake them up."),
        HumanMessage(content="The platform target is Android. We can defer iOS to v2."),
        HumanMessage(content="Yes, Vertex AI for the voice synthesis sounds right."),
        HumanMessage(content="Firebase auth is fine. Email + Google sign-in only."),
        HumanMessage(content="The friction Hugo found makes sense. The battery optimizer killing the app is the #1 risk."),
        HumanMessage(content="Yes, single-user MVP. No social features for now."),
        HumanMessage(content="Let's draft the user stories. Show me 5-7 stories — role, goal, value, acceptance."),
    ]


async def _one_run(model_name: str, system_msg: SystemMessage, msgs: list, *, label: str) -> dict:
    """Run a single LLM call and return measured usage."""
    print(f"\n  -> [{label}] sending to model {model_name}...")
    llm = init_chat_model(
        f"google_vertexai:{model_name}",
        project=settings.gcp_project_id,
        location=settings.vertex_location,
        max_output_tokens=1024,
        # langchain-google-vertexai doesn't yet expose `thinking_level` —
        # using `thinking_budget=-1` (dynamic) matches production Maya.
        thinking_budget=-1,
    )
    t0 = time.perf_counter()
    response = await llm.ainvoke([system_msg, *msgs])
    elapsed = time.perf_counter() - t0
    usage = _pull_usage(response)
    cost = _estimate_cost(model_name, usage["prompt_tokens"], usage["cached_tokens"], usage["completion_tokens"])
    print(f"     latency       : {elapsed:.1f}s")
    print(f"     prompt tokens : {usage['prompt_tokens']:>8,}    (cached: {usage['cached_tokens']:>6,})")
    print(f"     output tokens : {usage['completion_tokens']:>8,}    (thoughts: {usage['thoughts_tokens']:>6,})")
    print(f"     est. USD cost : ${cost:.4f}")
    return {**usage, "cost": cost, "latency_s": elapsed, "model": model_name}


async def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else settings.maya_model
    print("\n" + "#" * 72)
    print(f"#  Cost comparison run — label: {label}")
    print(f"#  Model from settings.maya_model: {settings.maya_model}")
    print("#" * 72)

    # Build the exact prompt structure Maya uses: system + state-block,
    # then conversation messages.
    full_system = prompts.MAYA + _synthetic_state_block()
    system_msg = SystemMessage(content=full_system)
    msgs = _synthetic_messages()

    # Quick stat about prompt size
    chars = len(full_system)
    print(f"\n  system prompt + state block size: {chars:,} chars (~{chars // 4:,} est. tokens)")
    print(f"  prior messages count            : {len(msgs)}")

    # Two consecutive runs. Second one SHOULD see cache hit if the model
    # supports implicit caching (Gemini Pro/Flash do, automatically, with
    # a ~5min TTL on prefixes ≥1024 tokens).
    r1 = await _one_run(settings.maya_model, system_msg, msgs, label=f"{label} run 1 (cold)")
    print("  -> waiting 2s before run 2 (cache warmth check)...")
    await asyncio.sleep(2)
    r2 = await _one_run(settings.maya_model, system_msg, msgs, label=f"{label} run 2 (warm)")

    print("\n" + "=" * 72)
    print(f"  SUMMARY for {label}")
    print("=" * 72)
    total_cost = r1["cost"] + r2["cost"]
    avg_cost = total_cost / 2
    print(f"  Per-call avg cost: ${avg_cost:.4f}")
    print(f"  Per-call avg tokens: prompt={(r1['prompt_tokens']+r2['prompt_tokens'])//2:,}, output={(r1['completion_tokens']+r2['completion_tokens'])//2:,}")
    cache_hit_rate = (r2["cached_tokens"] / r2["prompt_tokens"] * 100) if r2["prompt_tokens"] else 0
    print(f"  Cache hit on run 2: {r2['cached_tokens']:,} / {r2['prompt_tokens']:,} tokens ({cache_hit_rate:.0f}%)")
    if cache_hit_rate > 0:
        print(f"     ^^ IMPLICIT CACHE IS WORKING")
    else:
        print(f"     ^^ no cache hit (prompt may be < 1024 tokens or model doesn't auto-cache)")

    # Stash machine-readable so a second invocation can diff
    out_path = os.path.join(os.path.dirname(__file__), f"cost_compare_{label.replace('/', '-').replace(':', '-')}.json")
    with open(out_path, "w") as f:
        json.dump({"label": label, "r1": r1, "r2": r2, "avg_cost": avg_cost}, f, indent=2)
    print(f"\n  results saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
