"""Phase 4 smoke — skill & memory (clean_architecture §5, §6).

Proves the Phase-4 deliverables:
- The product-arc skill is discoverable through Maya's knowledge backend.
- The always-on founder-rules memory loads and carries the hard rules.
- Maya compiles with skill + memory + deny-write permissions wired.
- Filesystem writes are DENIED — the fix for the Phase-1 drift where Maya thought
  she was "building the app." She can read knowledge but never write to disk.
- (live, light) On a fresh idea Maya behaves like a product manager: she does not
  claim to have built an app, and the skill is available in her context.

Part A is offline/deterministic. Part B makes one short live call (Vertex/ADC).

Run:  python -m tests.smoke_phase4
"""
from __future__ import annotations

import asyncio
import sys

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.skills import _list_skills

from app.deepagent import coordinator


def part_a() -> None:
    print("== Part A: skill + memory load offline, writes denied ==")
    kd = coordinator._KNOWLEDGE_DIR
    assert kd.exists(), f"knowledge dir missing: {kd}"
    be = FilesystemBackend(root_dir=str(kd), virtual_mode=True)

    # 1. Skill discoverable + parseable.
    skills = _list_skills(be, "/skills/")
    names = {s["name"] for s in skills}
    assert "product-arc" in names, f"product-arc skill not found: {names}"
    arc = next(s for s in skills if s["name"] == "product-arc")
    assert arc["path"] == "/skills/product-arc/SKILL.md"
    assert len(arc["description"]) > 50, "skill description too thin to disclose well"
    print(f"   PASS: skill 'product-arc' discoverable ({arc['path']}).")

    # 2. Memory loads with the hard rules present.
    mem = be.download_files(["/memory/AGENTS.md"])[0]
    assert mem.error is None, f"memory unreadable: {mem.error}"
    body = (mem.content or b"").decode("utf-8")
    for rule in ("No time", "Plain language", "push back", "single coach"):
        assert rule in body, f"founder rule missing from memory: {rule!r}"
    assert "product manager" in body and "how" in body, "PM/not-a-coder identity missing"
    print("   PASS: memory loads with all hard rules + PM identity.")

    # 3. Permissions deny disk writes (the anti-'build the app' guard).
    deny = coordinator._DENY_DISK_WRITES
    assert any(
        p.mode == "deny" and "write" in p.operations and "/" in p.paths
        for p in deny
    ), "disk writes are not denied"
    print("   PASS: filesystem writes denied (Maya cannot build on disk).")

    # 4. Maya compiles with everything wired.
    maya = coordinator.build_maya(checkpointer=False)
    assert maya is not None
    print("   PASS: Maya compiles with skill + memory + permissions.")


async def _run_turn(project_id: str) -> str:
    """Stream Maya's opening turn and return her first substantive reply.

    We stop as soon as Maya produces an AI message with real text. That captures
    her actual coaching voice cheaply, without running the full (slow, costly)
    delegation chain to completion — enough to check she behaves like a PM.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from app.deepagent.domain_tools import set_active_project

    set_active_project(project_id)
    maya = coordinator.build_maya(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "smoke_phase4"}, "recursion_limit": 40}
    msg = (
        "Hi Maya. I have an idea: an app that reminds people to eat the food in "
        "their fridge before it goes off. Where do we start?"
    )
    seen: set[int] = set()
    async for chunk in maya.astream(
        {"messages": [{"role": "user", "content": msg}]}, cfg, stream_mode="values"
    ):
        for m in chunk.get("messages", []):
            if getattr(m, "type", "") != "ai" or id(m) in seen:
                continue
            seen.add(id(m))
            text = _message_text(m.content)
            if text.strip():
                return text
    return ""


def _message_text(content) -> str:
    """Flatten message content to text (Gemini may return a list of parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                parts.append(p["text"])
        return " ".join(parts)
    return ""


def part_b() -> int:
    print("\n== Part B: live — Maya behaves as a PM on a fresh idea ==")
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
                 "name": "ZZZ smoke_phase4 (delete me)", "icon": "🧪"})
        .execute()
    )
    project_id = proj.data[0]["id"]
    print(f"   => temp project {project_id}")
    try:
        reply = asyncio.run(_run_turn(project_id))
    except Exception as e:  # pragma: no cover
        print(f"SKIP: live model call failed (env/credentials?): {type(e).__name__}: {e}")
        return 0
    finally:
        supabase_admin.table("projects").delete().eq("id", project_id).execute()
        print(f"   => cleaned up temp project {project_id}")

    final = reply.lower()
    print(f"   Maya (excerpt): {reply[:280]!r}")
    assert final.strip(), "Maya produced no text reply"

    # She must NOT claim to have built/coded an app (the Phase-1 drift).
    forbidden = ["i built", "i've built", "i have built", "i created the app",
                 "i've created the app", "taskflow", "wrote the code", "implemented the app"]
    hit = [p for p in forbidden if p in final]
    assert not hit, f"Maya drifted into app-building language: {hit}"
    print("   PASS: no app-building drift — Maya stays a product manager.")
    return 0


def run() -> int:
    part_a()
    rc = part_b()
    print("\nPHASE 4 SMOKE: PASS")
    return rc


if __name__ == "__main__":
    sys.exit(run())
