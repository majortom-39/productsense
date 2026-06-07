"""Phase 5 frontend e2e — proves every NEW backend surface the dashboard
consumes actually works against a live Supabase, end to end:

  1. Service layer: list_solutions / list_features / list_reviews return the
     right rows in the right order, with the review-enrichment (title +
     display_id) resolved from each node's physical table.
  2. depgraph review flow: create nodes -> wire a dependency -> flag_change
     -> the dependent surfaces in list_reviews with a human title.
  3. HTTP layer: GET /projects/{id}/solutions|features|reviews respond 200
     with the documented JSON envelope (the exact shape lib/api.ts decodes),
     and enforce ownership (403 for a stranger).
  4. Full Maya turn: a real founder message streams text_delta -> message ->
     turn_done with no error (single-voice coordinator still healthy after
     the frontend wiring changes).

Everything runs on a throwaway project that is hard-deleted at the end
(cascades to all seeded rows). Run:

    python -m tests.e2e_phase5_frontend
"""
from __future__ import annotations

import asyncio
import sys
import traceback

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# conftest side-effects (env load) — import for the .env bootstrap.
import tests.conftest  # noqa: F401

from app.db import supabase_admin
from app.services import artifacts as svc
from app.deepagent import depgraph
from app.deepagent import domain_tools as dt


def _tool(fn):
    """Unwrap a LangChain @tool to its raw python callable."""
    return getattr(fn, "func", fn)


def _seed(pid: str) -> dict:
    """Seed one of each node type via the real domain tools, bound to pid.
    Returns the refs/ids we'll assert against."""
    dt.set_active_project(pid)

    create_solution = _tool(dt.create_solution)
    create_feature = _tool(dt.create_feature)
    log_decision = _tool(dt.log_decision) if hasattr(dt, "log_decision") else None

    # Two solutions; the second is the recommended one (tests ordering).
    s1 = create_solution("Manual reminder list", "User keeps their own list.", False, None)
    s2 = create_solution("Smart schedule", "We compute a watering schedule.", True, None)
    sol2_ref = s2.split("(")[1].split(")")[0]  # 'solution:<uuid>'
    sol2_id = sol2_ref.split(":", 1)[1]

    # Two features off the recommended solution; one in MVP, one not.
    f1 = create_feature("Plant profiles", "Store each plant + its needs.", True, [sol2_ref])
    f2 = create_feature("Weather sync", "Adjust schedule to local weather.", False, [sol2_ref])
    feat1_ref = f1.split("(")[1].split(")")[0]
    feat1_id = feat1_ref.split(":", 1)[1]

    return {
        "sol2_id": sol2_id,
        "sol2_ref": sol2_ref,
        "feat1_id": feat1_id,
        "feat1_ref": feat1_ref,
        "s1": s1, "s2": s2, "f1": f1, "f2": f2,
    }


def test_service_layer(pid: str, seeded: dict) -> None:
    print("\n== 1. Service layer ==")
    sols = svc.list_solutions(pid)
    assert len(sols) == 2, f"expected 2 solutions, got {len(sols)}"
    # recommended-first ordering
    assert sols[0]["recommended"] is True, "recommended solution must sort first"
    assert sols[0]["display_id"] == "sol-2"
    assert {"id", "display_id", "title", "summary", "recommended", "needs_review"} <= sols[0].keys()
    print(f"   PASS: list_solutions -> 2 rows, recommended-first ({sols[0]['display_id']}).")

    feats = svc.list_features(pid)
    assert len(feats) == 2, f"expected 2 features, got {len(feats)}"
    assert feats[0]["in_mvp"] is True, "in_mvp feature must sort first"
    assert {"id", "display_id", "title", "description", "in_mvp", "needs_review"} <= feats[0].keys()
    print(f"   PASS: list_features -> 2 rows, MVP-first ({feats[0]['display_id']}).")

    # No reviews yet (nothing flagged)
    assert svc.list_reviews(pid) == [], "no nodes flagged yet -> reviews must be empty"
    print("   PASS: list_reviews -> [] before any flag.")


def test_review_flow(pid: str, seeded: dict) -> None:
    print("\n== 2. depgraph review flow ==")
    # feature1 derives_from solution2 (wired at creation). Materially change
    # the solution -> its dependents (feature1) should flag for review.
    flag_change = _tool(dt.flag_change)
    out = flag_change(seeded["sol2_ref"], "Switched scheduling approach")
    print(f"   flag_change -> {out!r}")

    raw = depgraph.list_needs_review(pid)
    assert raw, "expected at least one flagged node after flag_change"
    assert any(r["id"] == seeded["feat1_id"] for r in raw), \
        "feature1 (dependent of solution2) should be flagged"
    print(f"   PASS: depgraph flagged {len(raw)} node(s); feature1 among them.")

    # The enriched surface the dashboard renders.
    reviews = svc.list_reviews(pid)
    feat_review = next((r for r in reviews if r["id"] == seeded["feat1_id"]), None)
    assert feat_review is not None, "list_reviews dropped the flagged feature"
    assert feat_review["title"] == "Plant profiles", \
        f"review title not enriched: {feat_review!r}"
    assert feat_review["display_id"] == "f-1", \
        f"review display_id not enriched: {feat_review!r}"
    assert feat_review["why"], "review why missing"
    assert {"type", "id", "why", "title", "display_id"} == set(feat_review.keys()), \
        f"review shape mismatch (frontend ReviewItem): {feat_review.keys()}"
    print(f"   PASS: list_reviews enriched -> {feat_review!r}")


def test_http_layer(pid: str, user_id: str) -> None:
    print("\n== 3. HTTP route layer (TestClient + auth override) ==")
    from fastapi.testclient import TestClient
    import main
    from app.services.auth import current_user_id

    # Override the JWT dependency to return our known owner.
    main.app.dependency_overrides[current_user_id] = lambda: user_id
    try:
        client = TestClient(main.app)
        h = {"Authorization": "Bearer test"}  # value irrelevant; dep overridden

        r = client.get(f"/projects/{pid}/solutions", headers=h)
        assert r.status_code == 200, f"solutions -> {r.status_code}: {r.text}"
        body = r.json()
        assert "solutions" in body and len(body["solutions"]) == 2, body
        print("   PASS: GET /solutions 200, envelope {solutions:[...]} len 2.")

        r = client.get(f"/projects/{pid}/features", headers=h)
        assert r.status_code == 200, f"features -> {r.status_code}: {r.text}"
        body = r.json()
        assert "features" in body and len(body["features"]) == 2, body
        print("   PASS: GET /features 200, envelope {features:[...]} len 2.")

        r = client.get(f"/projects/{pid}/reviews", headers=h)
        assert r.status_code == 200, f"reviews -> {r.status_code}: {r.text}"
        body = r.json()
        assert "reviews" in body and len(body["reviews"]) >= 1, body
        print(f"   PASS: GET /reviews 200, envelope {{reviews:[...]}} len {len(body['reviews'])}.")

        # Ownership: a stranger must NOT read this project's data.
        main.app.dependency_overrides[current_user_id] = lambda: "00000000-0000-0000-0000-000000000000"
        r = client.get(f"/projects/{pid}/solutions", headers=h)
        assert r.status_code in (403, 404), f"stranger got {r.status_code} (expected 403/404)"
        print(f"   PASS: stranger blocked from /solutions ({r.status_code}).")
    finally:
        main.app.dependency_overrides.pop(current_user_id, None)


async def _drive_maya(pid: str) -> list[dict]:
    from app.deepagent.session import DeepMayaSession
    s = DeepMayaSession(pid)
    s.start(send_greeting=True)
    await s.send(
        "Hi Maya. My idea helps people remember to water houseplants. In one "
        "sentence, what's the first thing we should figure out? Keep it short."
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


def test_full_maya_turn(pid: str) -> None:
    print("\n== 4. Full Maya turn (live stream) ==")
    from app.deepagent import session as sess
    events = asyncio.run(_drive_maya(pid))
    types = [e["type"] for e in events]
    print(f"   event types: {types}")
    errors = [e for e in events if e["type"] == "error"]
    assert not errors, f"Maya emitted error(s): {[e.get('message') for e in errors]}"
    msgs = [e for e in events if e["type"] == "message"]
    non_greeting = [m for m in msgs if m.get("content") != sess._GREETING]
    assert non_greeting, "Maya streamed no substantive reply"
    assert any(e["type"] == "text_delta" for e in events), "no token streaming"
    assert any(e["type"] == "turn_done" for e in events), "turn never closed"
    print(f"   PASS: greeting + {len(non_greeting)} reply, streamed, closed cleanly.")
    print(f"   Maya (excerpt): {(non_greeting[-1].get('content') or '')[:140]!r}")


def run() -> int:
    if supabase_admin is None:
        print("SKIP: Supabase admin client not configured.")
        return 0
    borrow = supabase_admin.table("projects").select("user_id").limit(1).execute()
    if not borrow.data:
        print("SKIP: no existing project to borrow a user_id from.")
        return 0
    user_id = borrow.data[0]["user_id"]
    proj = (
        supabase_admin.table("projects")
        .insert({"user_id": user_id, "name": "ZZZ e2e_phase5 (delete me)", "icon": "🧪"})
        .execute()
    )
    pid = proj.data[0]["id"]
    print(f"== e2e on throwaway project {pid} (owner {user_id}) ==")
    rc = 0
    try:
        seeded = _seed(pid)
        test_service_layer(pid, seeded)
        test_review_flow(pid, seeded)
        test_http_layer(pid, user_id)
        test_full_maya_turn(pid)
        print("\nPHASE 5 FRONTEND E2E: PASS")
    except Exception:
        rc = 1
        print("\nPHASE 5 FRONTEND E2E: FAIL")
        traceback.print_exc()
    finally:
        supabase_admin.table("projects").delete().eq("id", pid).execute()
        print(f"== cleaned up throwaway project {pid} ==")
    return rc


if __name__ == "__main__":
    sys.exit(run())
