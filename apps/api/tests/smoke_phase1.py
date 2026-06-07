"""Phase 1 smoke test — Maya coordinator + ask_founder interrupt round-trip.

Gate: the founder can be asked mid-run and the run resumes with their answer.

Run:  python -m tests.smoke_phase1
Needs Vertex ADC (gcloud auth application-default login).
"""
from __future__ import annotations

import sys

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.deepagent.coordinator import build_maya


def main() -> int:
    saver = InMemorySaver()
    maya = build_maya(checkpointer=saver)
    config = {"configurable": {"thread_id": "smoke-phase1"}}

    # A prompt that forces an ask_founder call so the interrupt path is exercised
    # deterministically.
    prompt = (
        "I want to build an app. Before you say anything else, you MUST call the "
        "ask_founder tool to ask me which platform I'm targeting (web or mobile). "
        "Do not answer or plan until you have asked."
    )

    print("=> First turn (expect an interrupt)...")
    result = maya.invoke({"messages": [HumanMessage(prompt)]}, config=config)

    interrupts = result.get("__interrupt__")
    if not interrupts:
        print("FAIL: no interrupt raised. Maya did not pause to ask the founder.")
        _dump_last_message(result)
        return 1

    intr = interrupts[0]
    payload = getattr(intr, "value", intr)
    print(f"   interrupt payload: {payload}")
    if not (isinstance(payload, dict) and payload.get("kind") == "ask_founder"):
        print("FAIL: interrupt was not an ask_founder request.")
        return 1
    print("   PASS: Maya paused with an ask_founder question.")

    # Drain interrupts: keep answering until the run completes. Proves the
    # resume round-trip works (possibly more than once if Maya asks follow-ups).
    answers = ["Web", "A simple to-do list app", "Yes, that's right"]
    resumed = result
    for i in range(5):
        ans = answers[min(i, len(answers) - 1)]
        print(f"=> Resuming with the founder's answer ({ans!r})...")
        resumed = maya.invoke(Command(resume={"answer": ans}), config=config)
        pending = resumed.get("__interrupt__")
        if not pending:
            break
        nxt = getattr(pending[0], "value", pending[0])
        print(f"   Maya asked again: {nxt.get('question') if isinstance(nxt, dict) else nxt!r}")
    else:
        print("FAIL: Maya kept interrupting after 5 answers.")
        return 1

    final = _last_ai_text(resumed)
    if not final:
        print("FAIL: no assistant text after resume.")
        _dump_last_message(resumed)
        return 1

    print(f"   final assistant text: {final[:200]!r}")
    print("   PASS: run resumed and completed after the founder's answer(s).")
    print("\nPHASE 1 SMOKE: PASS")
    return 0


def _last_ai_text(state: dict) -> str:
    for m in reversed(state.get("messages", [])):
        if m.__class__.__name__ == "AIMessage":
            c = m.content
            if isinstance(c, list):
                return " ".join(
                    p.get("text", "") for p in c if isinstance(p, dict)
                ).strip()
            if isinstance(c, str) and c.strip():
                return c.strip()
    return ""


def _dump_last_message(state: dict) -> None:
    msgs = state.get("messages", [])
    if msgs:
        last = msgs[-1]
        print(f"   last message: {type(last).__name__} -> {getattr(last, 'content', '')!r:.300}")


if __name__ == "__main__":
    sys.exit(main())
