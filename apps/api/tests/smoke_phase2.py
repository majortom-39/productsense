"""Phase 2 smoke — specialists return valid structured output via delegation.

Proves the Phase 2 gate's core: Maya delegates to a specialist through the
`task` tool, and the specialist's report comes back as a validated
`SpecialistResult` (JSON-serialized into the ToolMessage Maya receives).

Two parts:
  Part A (offline) — the SpecialistResult contract validates on BOTH branches
                     (complete / needs_input). Instant, no model calls.
  Part B (live)    — drive Maya to delegate to Nora (a synthesis-only specialist,
                     no web tools, so cheap + deterministic) and confirm a valid
                     SpecialistResult lands in a ToolMessage.

Run:  python -m tests.smoke_phase2
Needs Vertex ADC for Part B.
"""
from __future__ import annotations

import sys

from pydantic import ValidationError

from app.deepagent.contracts import SpecialistResult


def part_a_contract() -> int:
    """Offline: both branches of the structured contract validate."""
    print("=> Part A: SpecialistResult contract (offline)...")

    complete = SpecialistResult(
        status="complete",
        summary="Drafted a 3-bullet PRD outline.",
        detail="- Problem\n- Audience\n- MVP scope",
    )
    needs = SpecialistResult(
        status="needs_input",
        summary="Can't proceed without the target platform.",
        questions=["Is this web or mobile?"],
    )

    # Round-trip through JSON exactly as the task tool serializes it.
    for obj in (complete, needs):
        reparsed = SpecialistResult.model_validate_json(obj.model_dump_json())
        assert reparsed.status in ("complete", "needs_input")
        assert reparsed.summary

    # Status is constrained — a bogus value must be rejected.
    try:
        SpecialistResult(status="banana", summary="x")  # type: ignore[arg-type]
    except ValidationError:
        pass
    else:
        print("FAIL: invalid status was accepted.")
        return 1

    print("   PASS: complete + needs_input validate; bad status rejected.")
    return 0


def _find_specialist_results(messages: list) -> list[SpecialistResult]:
    """Any ToolMessage whose content parses as a SpecialistResult."""
    found = []
    for m in messages:
        if m.__class__.__name__ != "ToolMessage":
            continue
        content = m.content if isinstance(m.content, str) else str(m.content)
        try:
            found.append(SpecialistResult.model_validate_json(content))
        except (ValidationError, ValueError):
            continue
    return found


def part_b_delegation() -> int:
    """Live: Maya delegates to Nora and gets back a structured report."""
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from app.deepagent.coordinator import build_maya

    print("=> Part B: Maya delegates to a specialist (live)...")
    maya = build_maya(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "smoke-phase2"}}
    prompt = (
        "Use the task tool to delegate to the 'nora' specialist. Ask Nora to "
        "draft a short PRD outline (3-4 bullets) for a simple habit-tracking "
        "app for busy parents. You have enough context — do NOT call "
        "ask_founder, and tell Nora not to ask for clarification. After Nora "
        "reports back, give me a one-line confirmation."
    )

    result = maya.invoke({"messages": [HumanMessage(prompt)]}, config=config)

    # Drain any ask_founder interrupts so the run completes (shouldn't fire,
    # but be resilient).
    for _ in range(3):
        if not result.get("__interrupt__"):
            break
        result = maya.invoke(Command(resume={"answer": "Proceed with your best judgment."}), config=config)

    results = _find_specialist_results(result.get("messages", []))
    if not results:
        print("FAIL: no SpecialistResult found in any ToolMessage.")
        for m in result.get("messages", []):
            print(f"   {m.__class__.__name__}: {str(getattr(m, 'content', ''))[:120]}")
        return 1

    sr = results[0]
    print(f"   delegated -> status={sr.status!r}, summary={sr.summary[:80]!r}")
    if sr.status not in ("complete", "needs_input") or not sr.summary:
        print("FAIL: SpecialistResult present but invalid shape.")
        return 1

    print(f"   PASS: {len(results)} valid SpecialistResult(s) returned via delegation.")
    return 0


def main() -> int:
    if part_a_contract() != 0:
        return 1
    if part_b_delegation() != 0:
        return 1
    print("\nPHASE 2 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
