"""The dependency graph engine — the coherence plumbing (clean_architecture §8).

A single directed graph over every product node. Two responsibilities, both
deliberately dumb and reliable; the *judgment* about what to do lives one layer
up, in Maya.

1. **Edges at birth.** `add_dependency` records that one node derives from /
   is constrained by / supersedes another. Creation tools call this as a side
   effect of producing a node, so an edge can't be forgotten.
2. **Lazy dirty-marking.** When a node is materially changed,
   `mark_dependents_for_review` flags its DIRECT dependents `needs_review` with a
   reason — and stops there. It never paints the whole graph red; propagation
   continues only when a flagged node is itself changed during review. Nothing is
   ever auto-rewritten.

Every node table carries `needs_review` / `needs_review_why` / `version`, so a
node is addressable generically by `(type, id)`.
"""
from __future__ import annotations

from typing import Literal

from app.db import require_admin

Relationship = Literal["derives_from", "constrains", "supersedes"]

# Node type -> physical table. Adding a node kind is a one-line change here.
# Guardrails are decisions tagged 'guardrail', so they live in the same table.
NODE_TABLES: dict[str, str] = {
    "artifact": "discovery_artifacts",
    "decision": "decisions",
    "guardrail": "decisions",
    "task": "tasks",
    "prd_section": "prd_sections",
    "solution": "solutions",
    "feature": "features",
}


def _table_for(node_type: str) -> str:
    table = NODE_TABLES.get(node_type)
    if table is None:
        raise ValueError(
            f"Unknown node type {node_type!r}. Known: {', '.join(NODE_TABLES)}"
        )
    return table


def parse_ref(ref: str) -> tuple[str, str]:
    """'type:id' -> (type, id), validating the type is a known node kind."""
    if ":" not in ref:
        raise ValueError(f"Node ref must be 'type:id', got {ref!r}")
    node_type, node_id = ref.split(":", 1)
    node_type = node_type.strip()
    if node_type not in NODE_TABLES:
        raise ValueError(
            f"Unknown node type {node_type!r} in ref {ref!r}. "
            f"Known: {', '.join(NODE_TABLES)}"
        )
    return node_type, node_id.strip()


def fetch_node(project_id: str, node_type: str, node_id: str) -> dict | None:
    """Read one node row from its physical table, scoped to the project.

    `prd_sections` has no `project_id` column (it's scoped via its parent prd),
    so it's fetched by id alone; every other node table is project-scoped.
    """
    table = NODE_TABLES.get(node_type)
    if not table:
        return None
    db = require_admin()
    q = db.table(table).select("*").eq("id", node_id)
    if table != "prd_sections":
        q = q.eq("project_id", project_id)
    try:
        row = q.maybe_single().execute()
    except Exception:
        return None
    return row.data if row else None


def node_exists(project_id: str, node_type: str, node_id: str) -> bool:
    """Does this `(type, id)` actually name a live row in this project?

    The guard that stops a hallucinated ref from writing a phantom edge.
    Most node tables carry `project_id`; `prd_sections` is scoped through its
    parent `prds` row, so we resolve it via the project's prd ids.
    """
    table = _table_for(node_type)
    db = require_admin()
    q = db.table(table).select("id").eq("id", node_id).limit(1)
    if table == "prd_sections":
        prds = db.table("prds").select("id").eq("project_id", project_id).execute()
        prd_ids = [p["id"] for p in (prds.data or [])]
        if not prd_ids:
            return False
        q = q.in_("prd_id", prd_ids)
    else:
        q = q.eq("project_id", project_id)
    try:
        rows = q.execute()
    except Exception:
        # A malformed id (e.g. not a uuid) can't name a real node — treat the
        # ref as non-existent rather than letting the DB error escape.
        return False
    return bool(rows.data)


def add_dependency(
    *,
    project_id: str,
    dependent_type: str,
    dependent_id: str,
    depends_on_type: str,
    depends_on_id: str,
    relationship: Relationship,
    created_by: str,
    why: str | None = None,
) -> dict:
    """Record one edge: `dependent` depends on `depends_on`.

    Validates both node types are known AND both ids exist in this project, so
    neither a typo nor a hallucinated ref can create a phantom edge.
    """
    _table_for(dependent_type)
    _table_for(depends_on_type)
    if not node_exists(project_id, dependent_type, dependent_id):
        raise ValueError(f"No such node {dependent_type}:{dependent_id} in this project.")
    if not node_exists(project_id, depends_on_type, depends_on_id):
        raise ValueError(f"No such node {depends_on_type}:{depends_on_id} in this project.")
    db = require_admin()
    row = (
        db.table("dependencies")
        .insert(
            {
                "project_id": project_id,
                "dependent_type": dependent_type,
                "dependent_id": dependent_id,
                "depends_on_type": depends_on_type,
                "depends_on_id": depends_on_id,
                "relationship": relationship,
                "created_by": created_by,
                "why": why,
            }
        )
        .execute()
    )
    return (row.data or [{}])[0]


def direct_dependents(project_id: str, node_type: str, node_id: str) -> list[dict]:
    """Edges whose `depends_on` is this node — i.e. what would be affected if it
    changed. One hop only."""
    db = require_admin()
    rows = (
        db.table("dependencies")
        .select("dependent_type,dependent_id,relationship,why")
        .eq("project_id", project_id)
        .eq("depends_on_type", node_type)
        .eq("depends_on_id", node_id)
        .execute()
    )
    return rows.data or []


def provenance(project_id: str, node_type: str, node_id: str) -> list[dict]:
    """Edges this node depends on — what it was derived from / constrained by."""
    db = require_admin()
    rows = (
        db.table("dependencies")
        .select("depends_on_type,depends_on_id,relationship,why")
        .eq("project_id", project_id)
        .eq("dependent_type", node_type)
        .eq("dependent_id", node_id)
        .execute()
    )
    return rows.data or []


def mark_dependents_for_review(
    project_id: str, node_type: str, node_id: str, reason: str
) -> list[dict]:
    """Flag this node's DIRECT dependents `needs_review`. Lazy — stops at one hop.

    Returns the list of nodes flagged so the caller can report impact to Maya.
    Propagation past the first hop happens only if/when a flagged node is itself
    materially changed (which calls this again for *its* dependents).
    """
    deps = direct_dependents(project_id, node_type, node_id)
    db = require_admin()
    flagged: list[dict] = []
    for dep in deps:
        dtype = dep["dependent_type"]
        did = dep["dependent_id"]
        why = (
            f"{node_type} it {dep['relationship']} changed: {reason}"
            if dep.get("relationship")
            else reason
        )
        (
            db.table(_table_for(dtype))
            .update({"needs_review": True, "needs_review_why": why})
            .eq("id", did)
            .execute()
        )
        flagged.append({"type": dtype, "id": did, "why": why})
    return flagged


def bump_version(project_id: str, node_type: str, node_id: str) -> int:
    """Increment a node's version (its row already exists). Returns new version."""
    db = require_admin()
    table = _table_for(node_type)
    cur = db.table(table).select("version").eq("id", node_id).single().execute()
    new_version = int((cur.data or {}).get("version", 1)) + 1
    db.table(table).update({"version": new_version}).eq("id", node_id).execute()
    return new_version


def clear_needs_review(project_id: str, node_type: str, node_id: str) -> None:
    """Mark a node reviewed — clear its flag once Maya has acted on it."""
    db = require_admin()
    (
        db.table(_table_for(node_type))
        .update({"needs_review": False, "needs_review_why": None})
        .eq("id", node_id)
        .execute()
    )


def list_needs_review(project_id: str) -> list[dict]:
    """Every flagged node across all tables, for the review surface / Maya."""
    db = require_admin()
    out: list[dict] = []
    seen_tables: set[str] = set()
    for node_type, table in NODE_TABLES.items():
        if table in seen_tables:
            continue
        seen_tables.add(table)
        q = db.table(table).select("id,needs_review_why").eq("needs_review", True)
        # Most node tables carry project_id directly; prd_sections is scoped
        # through its parent prds row, so filter by that project's prd ids.
        if table == "prd_sections":
            prds = db.table("prds").select("id").eq("project_id", project_id).execute()
            prd_ids = [p["id"] for p in (prds.data or [])]
            if not prd_ids:
                continue
            q = q.in_("prd_id", prd_ids)
        else:
            q = q.eq("project_id", project_id)
        rows = q.execute()
        for r in rows.data or []:
            out.append({"type": node_type, "id": r["id"], "why": r.get("needs_review_why")})
    return out
