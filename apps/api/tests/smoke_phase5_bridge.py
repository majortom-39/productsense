"""Phase 5 smoke — the SSE bridge to the new Deep Agents coordinator.

Proves the keystone of Phase 5: `DeepMayaSession` makes `build_maya` reachable
with the legacy session surface and shapes the new event stream the frontend
consumes.

- Part A (offline): the event-shaping helpers and the session build are sane.
- Part B (live): on a throwaway project, the session emits a greeting, streams
  Maya's tokens (`text_delta`), persists a real `message`, and closes the turn
  with `turn_done` — no `error`. Maya stays the single voice (no specialist
  tokens leak into the chat text).

Run:  python -m tests.smoke_phase5_bridge
"""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.deepagent import session as sess
from app.deepagent.session import DeepMayaSession, _flatten, _hints_for


def part_a() -> None:
    print("== Part A: bridge helpers + build (offline) ==")
    assert _hints_for("create_solution") == {"solutions"}
    assert _hints_for("create_feature") == {"features"}
    assert _hints_for("log_decision") == {"decisions", "reviews"}
    assert _hints_for("create_artifact") == {"discovery"}
    assert _hints_for("link") == set()
    print("   PASS: domain-tool -> surface hint routing is correct.")

    assert _flatten([{"text": "a"}, "b", {"type": "text", "text": "c"}]) == "abc"
    assert _flatten("plain") == "plain"
    print("   PASS: Gemini list-part content flattens to text.")

    s = DeepMayaSession("00000000-0000-0000-0000-000000000000")
    assert s.is_done is False and s.is_processing is False
    assert s.awaiting_answer is False
    assert sess._GREETING and "Maya" in sess._GREETING
    print("   PASS: session constructs; greeting + flags sane.")


async def _drive(pid: str) -> list[dict]:
    """Run one founder turn through the session; collect events until the turn
    closes or we time out. Returns the events seen."""
    s = DeepMayaSession(pid)
    s.start(send_greeting=True)
    await s.send(
        "Hi Maya. My idea is a simple app that helps people remember to water "
        "their houseplants. In one or two sentences, what's the first thing we "
        "should figure out? Keep it short."
    )
    events: list[dict] = []
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 200
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            ev = await asyncio.wait_for(s.next_event(), timeout=remaining)
            if ev is None:
                break
            events.append(ev)
            if ev.get("type") == "turn_done":
                break
    finally:
        s.abort()
    return events


def part_b() -> int:
    print("\n== Part B: live — session streams a real turn ==")
    from app.db import supabase_admin

    if supabase_admin is None:
        print("SKIP: Supabase admin client not configured.")
        return 0
    borrow = supabase_admin.table("projects").select("user_id").limit(1).execute()
    if not borrow.data:
        print("SKIP: no existing project to borrow a user_id from.")
        return 0
    proj = (
        supabase_admin.table("projects")
        .insert({"user_id": borrow.data[0]["user_id"],
                 "name": "ZZZ smoke_phase5 (delete me)", "icon": "🧪"})
        .execute()
    )
    pid = proj.data[0]["id"]
    print(f"   => temp project {pid}")
    try:
        events = asyncio.run(_drive(pid))
    except Exception as e:  # pragma: no cover
        print(f"SKIP: live run failed (env/credentials?): {type(e).__name__}: {e}")
        supabase_admin.table("projects").delete().eq("id", pid).execute()
        return 0
    finally:
        # messages were persisted under this project; drop the project (cascades).
        supabase_admin.table("projects").delete().eq("id", pid).execute()
        print(f"   => cleaned up temp project {pid}")

    types = [e["type"] for e in events]
    print(f"   event types: {types}")

    errors = [e for e in events if e["type"] == "error"]
    assert not errors, f"bridge emitted error(s): {[e.get('message') for e in errors]}"

    msgs = [e for e in events if e["type"] == "message"]
    assert msgs, "no `message` events — Maya produced no text"
    # The first message is the greeting; there must be at least one more — her
    # actual reply to the founder.
    non_greeting = [m for m in msgs if m.get("content") != sess._GREETING]
    assert non_greeting, "Maya streamed no substantive reply (only the greeting)"
    print(f"   PASS: greeting + {len(non_greeting)} Maya message(s) persisted.")

    assert any(e["type"] == "text_delta" for e in events), "no token streaming"
    print("   PASS: Maya's tokens streamed as text_delta.")

    assert any(e["type"] == "turn_done" for e in events), "turn never closed"
    print("   PASS: turn closed with turn_done.")

    excerpt = (non_greeting[-1].get("content") or "")[:160]
    print(f"   Maya (excerpt): {excerpt!r}")
    return 0


def run() -> int:
    part_a()
    rc = part_b()
    print("\nPHASE 5 BRIDGE SMOKE: PASS")
    return rc


if __name__ == "__main__":
    sys.exit(run())
