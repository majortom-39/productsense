"""Phase 3 smoke — the coherence engine (clean_architecture §8).

Proves the gate: changing an upstream node flags the RIGHT dependents (its direct
ones only — propagation is lazy), and a flag can be cleared once acted on. Runs
against the live DB on a throwaway project that is deleted at the end (cascade
cleans every child row).

Exercises both layers: the `depgraph` engine and the `domain_tools` @tool surface
(so we know the tools Maya actually calls wire edges + propagate correctly).

Run:  python -m tests.smoke_phase3
Needs SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
"""
from __future__ import annotations

import sys

from app.db import supabase_admin
from app.deepagent import depgraph
from app.deepagent import domain_tools as dt


def _ref_id(tool_result: str) -> str:
    """Pull the node id out of a 'Created type:<id>: ...' tool message."""
    # e.g. "Created artifact:6f1c-...: Title" -> "6f1c-..."
    # robust parse: find a 'type:id' token (strip trailing punctuation first, since
    # the message is "Created type:<id>: Title" — the token carries a trailing ':').
    for raw in tool_result.replace(",", " ").replace("(", " ").replace(")", " ").split():
        token = raw.rstrip(".:")
        if token.count(":") == 1 and token.split(":", 1)[0] in depgraph.NODE_TABLES:
            return token.split(":", 1)[1]
    raise AssertionError(f"no node ref in: {tool_result!r}")


def _needs_review(table: str, node_id: str) -> dict:
    row = (
        supabase_admin.table(table)
        .select("needs_review,needs_review_why,version")
        .eq("id", node_id)
        .single()
        .execute()
    )
    return row.data or {}


def run() -> int:
    if supabase_admin is None:
        print("SKIP: Supabase admin client not configured.")
        return 0

    # A valid user_id is required by the projects FK; reuse an existing one.
    users = supabase_admin.table("projects").select("user_id").limit(1).execute()
    if not users.data:
        print("SKIP: no existing project to borrow a user_id from.")
        return 0
    user_id = users.data[0]["user_id"]

    proj = (
        supabase_admin.table("projects")
        .insert({"user_id": user_id, "name": "ZZZ smoke_phase3 (delete me)", "icon": "🧪"})
        .execute()
    )
    project_id = proj.data[0]["id"]
    print(f"=> temp project {project_id}")

    try:
        dt.set_active_project(project_id)

        # 1. Edge at birth: B derives from A.
        print("=> create A (problem), B derives_from A, C derives_from B...")
        a = _ref_id(dt.create_artifact.invoke(
            {"title": "Problem: users forget to log meals", "summary": "Validated pain."}
        ))
        b = _ref_id(dt.create_feature.invoke(
            {"title": "Quick-log button", "description": "One-tap meal log",
             "derived_from": [f"artifact:{a}"]}
        ))
        c = _ref_id(dt.create_feature.invoke(
            {"title": "Streak counter", "description": "Reward consistency",
             "derived_from": [f"feature:{b}"]}
        ))

        prov = depgraph.provenance(project_id, "feature", b)
        assert any(p["depends_on_id"] == a for p in prov), "B->A edge missing"
        deps = depgraph.direct_dependents(project_id, "artifact", a)
        assert any(d["dependent_id"] == b for d in deps), "A's dependents missing B"
        print("   PASS: edges captured at birth.")

        # 2. Material change to A flags its DIRECT dependents only (lazy).
        print("=> update A -> should flag B (direct), not C (grandchild)...")
        msg = dt.update_artifact.invoke(
            {"artifact_id": a, "summary": "Pain reframed: users forget to log SNACKS.",
             "reason": "Problem statement narrowed to snacks."}
        )
        assert f"feature:{b}" in msg, f"B not reported flagged: {msg}"
        assert _needs_review("features", b)["needs_review"] is True, "B not flagged in DB"
        assert _needs_review("features", c)["needs_review"] is False, "C wrongly flagged (not lazy)"
        assert _needs_review("discovery_artifacts", a)["version"] == 2, "A version not bumped"
        print("   PASS: only the direct dependent flagged; version bumped; lazy holds.")

        # 3. list_open_reviews surfaces B; resolve clears it.
        reviews = dt.list_open_reviews.invoke({})
        assert f"feature:{b}" in reviews, f"B missing from reviews: {reviews}"
        dt.resolve_review.invoke({"node": f"feature:{b}"})
        assert _needs_review("features", b)["needs_review"] is False, "B flag not cleared"
        print("   PASS: review listed and cleared.")

        # 4. Now that B was 'reviewed' and changed, flagging B propagates to C.
        print("=> flag_change on B -> should now flag C...")
        dt.flag_change.invoke({"node": f"feature:{b}", "reason": "Reworked after A changed."})
        assert _needs_review("features", c)["needs_review"] is True, "C not flagged on B change"
        print("   PASS: lazy propagation reaches next hop only when that hop changes.")

        # 5. log_decision with constrains wires a 'constrains' edge.
        dec = _ref_id(dt.log_decision.invoke(
            {"title": "MVP = quick-log only", "detail": "Cut streaks for MVP.",
             "why": "Smallest thing that delivers the core value.", "tag": "scope",
             "constrains": [f"feature:{b}"]}
        ))
        dec_prov = depgraph.direct_dependents(project_id, "decision", dec)
        assert any(d["dependent_id"] == b and d["relationship"] == "constrains" for d in dec_prov), \
            "constrains edge missing"
        print("   PASS: decision constrains-edge recorded.")

    finally:
        supabase_admin.table("projects").delete().eq("id", project_id).execute()
        print(f"=> cleaned up temp project {project_id}")

    print("\nPHASE 3 SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(run())
