"""Phase 1 durability smoke — interrupt round-trip on the real Postgres saver.

Proves the gate's persistence half: an ask_founder interrupt is checkpointed to
Supabase and resumes from durable state (a fresh agent instance, same thread_id).

Run:  python -m tests.smoke_phase1_postgres
Needs Vertex ADC + SUPABASE_DB_URL.
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.deepagent.checkpoint import postgres_saver
from app.deepagent.coordinator import build_maya


async def run() -> int:
    thread_id = "smoke-phase1-pg"
    config = {"configurable": {"thread_id": thread_id}}
    prompt = (
        "I want to build an app. Before anything else, you MUST call the "
        "ask_founder tool to ask which platform I'm targeting. Do not plan or "
        "answer until you've asked."
    )

    async with postgres_saver() as saver:
        if saver is None:
            print("SKIP: SUPABASE_DB_URL not set.")
            return 0

        # Turn 1 — fresh agent instance, expect an interrupt persisted to PG.
        maya1 = build_maya(checkpointer=saver)
        print("=> Turn 1 (expect interrupt, persisted to Postgres)...")
        result = await maya1.ainvoke({"messages": [HumanMessage(prompt)]}, config=config)
        if not result.get("__interrupt__"):
            print("FAIL: no interrupt raised.")
            return 1
        print("   PASS: interrupted and checkpointed.")

        # Turn 2 — brand new agent instance reads durable state and resumes.
        maya2 = build_maya(checkpointer=saver)
        print("=> Resuming from durable state with a NEW agent instance...")
        for i in range(5):
            resumed = await maya2.ainvoke(
                Command(resume={"answer": ["Web", "A to-do app", "Yes"][min(i, 2)]}),
                config=config,
            )
            if not resumed.get("__interrupt__"):
                break
        else:
            print("FAIL: still interrupting after 5 answers.")
            return 1

        has_ai = any(m.__class__.__name__ == "AIMessage" for m in resumed.get("messages", []))
        if not has_ai:
            print("FAIL: no assistant message after resume.")
            return 1

    print("   PASS: resumed from Postgres-checkpointed state to completion.")
    print("\nPHASE 1 POSTGRES SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
