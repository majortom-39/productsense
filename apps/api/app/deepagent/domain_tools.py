"""Maya's domain-action tools (clean_architecture §4).

These are the tools Maya uses to produce and maintain product nodes. Every
creation tool captures its dependency edges *at birth* (via `depgraph`), and
every material update flags the right dependents for review. The graph plumbing
is in `depgraph`; this module is the LangChain `@tool` surface over it plus the
node persistence.

Project scoping: the active project id is held in a contextvar set by the app
before it invokes Maya (`set_active_project`). Tools read it implicitly so the
model never has to pass — and can never spoof — the project id.

Node references in tool args use a compact `"type:id"` form
(e.g. `"artifact:6f1c..."`), so edges can be expressed as plain strings — which
Gemini handles far more reliably than nested objects.
"""
from __future__ import annotations

import contextvars
from datetime import datetime, timezone

from langchain_core.tools import tool

from app.db import require_admin
from app.deepagent import context_pack, depgraph
from app.services import artifacts as artifacts_service
from app.services import discovery_artifacts as da_service

# The render shapes Maya may choose for a synthesized card — the generic visual
# kinds the frontend `ArtifactRenderer` can draw (and a subset of the DB
# `render_kind_enum`): every kind here both stores and renders. Validated in the
# tool so a bad value gives Maya a clear message instead of a raw DB enum error.
MAYA_RENDER_KINDS: list[str] = [
    "text",           # {body_md}
    "table",          # {columns: [str], rows: [[cell]]}
    "matrix",         # {row_labels, col_labels, cells}
    "bar_chart",      # {categories, series:[{name, values:[num]}], x_label?, y_label?}
    "line_chart",     # {series:[{name, points:[{x, y}]}], x_label?, y_label?}
    "graph",          # {nodes:[{id, label, group?}], edges:[{from, to, label?}]}
    "persona_cards",  # {personas:[{name, role?, traits?, quote?, pains?}]}
    "stack_diagram",  # {layers:[{name, items:[str]}]}
    "mermaid",        # {source, caption?}
    "wireframe_flow", # the UX screens — see create_artifact docstring for the shape
]

# Set by the app/coordinator per run; tools read it implicitly.
_project_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "deepagent_project_id", default=None
)


def set_active_project(project_id: str) -> None:
    """Bind the active project for all domain-tool calls on this context."""
    _project_ctx.set(project_id)


def _project() -> str:
    pid = _project_ctx.get()
    if not pid:
        raise RuntimeError(
            "No active project bound. Call set_active_project(project_id) before "
            "invoking Maya."
        )
    return pid


def _parse_ref(ref: str) -> tuple[str, str]:
    """'type:id' -> (type, id), validating the type is a known node kind.

    Thin alias for `depgraph.parse_ref` so there's one implementation.
    """
    return depgraph.parse_ref(ref)


def _next_display_id(table: str, project_id: str, prefix: str, width: int = 0) -> str:
    """Generate the next sequential display id for a per-project table."""
    db = require_admin()
    rows = (
        db.table(table)
        .select("display_id")
        .eq("project_id", project_id)
        .execute()
    )
    n = len(rows.data or []) + 1
    return f"{prefix}{str(n).zfill(width)}" if width else f"{prefix}{n}"


def _wire_edges(
    node_ref: str, targets: list[str] | None, relationship: str, created_by: str
) -> list[str]:
    """Wire dependency edges between a new `node_ref` and its `targets`.

    Direction depends on the relationship, so the coherence engine flags the
    right side when something changes:
    - `derives_from`: the node depends on each target (node is the dependent),
      so changing a target flags the node.
    - `constrains`: the node constrains each target, so each *target* depends on
      the node — changing the node flags the targets.
    """
    if not targets:
        return []
    project_id = _project()
    ntype, nid = _parse_ref(node_ref)
    wired: list[str] = []
    for target in targets:
        ttype, tid = _parse_ref(target)
        if relationship == "constrains":
            dep_type, dep_id, on_type, on_id = ttype, tid, ntype, nid
        else:
            dep_type, dep_id, on_type, on_id = ntype, nid, ttype, tid
        depgraph.add_dependency(
            project_id=project_id,
            dependent_type=dep_type,
            dependent_id=dep_id,
            depends_on_type=on_type,
            depends_on_id=on_id,
            relationship=relationship,  # type: ignore[arg-type]
            created_by=created_by,
            why=None,
        )
        wired.append(target)
    return wired


def _missing_refs(refs: list[str] | None) -> list[str]:
    """Return the subset of `refs` that don't name a live node in this project.

    The pre-flight check tools run before wiring, so a hallucinated ref is
    reported to Maya rather than written as a phantom dependency edge.
    """
    if not refs:
        return []
    project_id = _project()
    missing: list[str] = []
    for ref in refs:
        try:
            rtype, rid = _parse_ref(ref)
        except ValueError:
            missing.append(ref)
            continue
        if not depgraph.node_exists(project_id, rtype, rid):
            missing.append(ref)
    return missing


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_node(node_type: str, node_id: str, project_id: str) -> dict | None:
    """Read one node row from its physical table, scoped to the project.

    Thin alias for `depgraph.fetch_node` (arg order kept for existing callers).
    """
    return depgraph.fetch_node(project_id, node_type, node_id)


def _fmt_node(node_type: str, row: dict) -> str:
    """One compact line for a node listing: '- type:id — D-001 Title v2 [needs_review]'."""
    ref = f"{node_type}:{row.get('id')}"
    disp = row.get("display_id")
    label = f"{disp} " if disp else ""
    title = row.get("title") or "(untitled)"
    version = row.get("version")
    vstr = f" v{version}" if version else ""
    flags = " [needs_review]" if row.get("needs_review") else ""
    return f"- {ref} — {label}{title}{vstr}{flags}"


def _soft_hide(node_type: str, node_id: str, project_id: str) -> None:
    """Soft-hide a node so it drops off its live listing — never destroys data.

    Artifacts/solutions/features use `deleted_at`; decisions/guardrails use
    `superseded_at` (the column their listing already filters on).
    """
    db = require_admin()
    if node_type == "artifact":
        da_service.delete(artifact_id=node_id, project_id=project_id)
    elif node_type in ("decision", "guardrail"):
        (
            db.table("decisions")
            .update({"superseded_at": _now_iso()})
            .eq("id", node_id)
            .eq("project_id", project_id)
            .execute()
        )
    elif node_type in ("solution", "feature"):
        (
            db.table(depgraph.NODE_TABLES[node_type])
            .update({"deleted_at": _now_iso()})
            .eq("id", node_id)
            .eq("project_id", project_id)
            .execute()
        )
    else:
        raise ValueError(f"Can't archive {node_type} nodes.")


# ── Artifacts ──────────────────────────────────────────────────────────────
@tool
def create_artifact(
    title: str,
    summary: str,
    render_kind: str = "text",
    payload: dict | None = None,
    derived_from: list[str] | None = None,
) -> str:
    """Create a discovery artifact (a research finding or product artifact).

    `render_kind` is the display shape — choose one of:
      text          — {body_md}
      table         — {columns: [str], rows: [[cell]]}
      matrix        — {row_labels, col_labels, cells}
      bar_chart     — {categories, series:[{name, values:[num]}], x_label?, y_label?}
      line_chart    — {series:[{name, points:[{x, y}]}], x_label?, y_label?}
      graph         — {nodes:[{id, label, group?}], edges:[{from, to, label?}]}
      persona_cards — {personas:[{name, role?, traits?, quote?, pains?}]}
      stack_diagram — {layers:[{name, items:[str]}]}
      mermaid       — {source, caption?}
      wireframe_flow — a UX screen flow (greyscale mockups). Shape:
          {device: "phone"|"browser"|"extension"|"desktop",
           flow_name?, flow_type?: "onboarding"|"core"|"settings"|"error"|"empty"|"auth"|"other",
           screens: [{name, html, notes?, derived_from?}],   # html = structural HTML for the screen body
           transitions?: [{from, to, trigger?}],
           informed_by?: [str]}
        Only draw screens AFTER the founder has signed off on the flow in chat,
        and make every element trace to a feature + the friction/pain it serves
        (use each screen's `derived_from` and the flow's `informed_by`). See the
        SCREENS step in the product-arc skill.
    `payload` carries the structured data for that shape (see above); for plain
    'text' you can pass {"body_md": "..."} or leave it empty and rely on summary.
    Never use a render_kind outside this list.

    `derived_from` is a list of node refs ('type:id') this artifact was produced
    from — those dependency edges are recorded automatically. Pass it whenever
    the artifact builds on earlier work; use list_nodes/get_node to find refs.

    Returns the new artifact's ref so you can wire further edges to it.
    """
    project_id = _project()
    if render_kind not in MAYA_RENDER_KINDS:
        return (
            f"Couldn't create — render_kind '{render_kind}' isn't allowed. "
            f"Choose one of: {', '.join(MAYA_RENDER_KINDS)}."
        )
    bad = _missing_refs(derived_from)
    if bad:
        return (
            f"Couldn't create — these derived_from refs don't exist: "
            f"{', '.join(bad)}. Use list_nodes/get_node to find valid refs."
        )
    row = da_service.create(
        project_id=project_id,
        title=title,
        render_kind=render_kind,
        payload=payload or {},
        summary=summary,
    )
    ref = f"artifact:{row['id']}"
    wired = _wire_edges(ref, derived_from, "derives_from", "maya")
    extra = f" (derived from {', '.join(wired)})" if wired else ""
    return f"Created {ref}: {title}{extra}"


@tool
def update_artifact(artifact_id: str, summary: str, reason: str) -> str:
    """Materially update an artifact's summary, then flag everything that
    derived from it for review.

    `reason` explains what changed and is shown on the review flags. Returns the
    list of dependents now flagged needs_review.
    """
    project_id = _project()
    db = require_admin()
    db.table("discovery_artifacts").update({"summary": summary}).eq("id", artifact_id).execute()
    depgraph.bump_version(project_id, "artifact", artifact_id)
    flagged = depgraph.mark_dependents_for_review(project_id, "artifact", artifact_id, reason)
    if not flagged:
        return f"Updated artifact:{artifact_id}. Nothing depended on it."
    refs = ", ".join(f"{f['type']}:{f['id']}" for f in flagged)
    return f"Updated artifact:{artifact_id}. Flagged for review: {refs}"


# ── Decisions ──────────────────────────────────────────────────────────────
@tool
def log_decision(
    title: str,
    detail: str,
    why: str,
    tag: str = "scope",
    derived_from: list[str] | None = None,
    constrains: list[str] | None = None,
) -> str:
    """Record a product decision ('we chose X because Z') as a first-class node.

    `tag` is one of 'scope' | 'guardrail' | 'technical' | 'flagged'.
    `derived_from`: node refs this decision was based on (edges recorded).
    `constrains`: node refs this decision limits (e.g. the features an MVP-cut
    decision keeps) — recorded as 'constrains' edges.

    Returns the decision's ref.
    """
    project_id = _project()
    bad = _missing_refs((derived_from or []) + (constrains or []))
    if bad:
        return (
            f"Couldn't log decision — these refs don't exist: {', '.join(bad)}. "
            "Use list_nodes/get_node to find valid refs."
        )
    db = require_admin()
    display_id = _next_display_id("decisions", project_id, "D-", width=3)
    row = (
        db.table("decisions")
        .insert(
            {
                "project_id": project_id,
                "display_id": display_id,
                "decided_by": "maya_autonomous",
                "status": "decided",
                "title": title,
                "detail": detail,
                "why": why,
                "tag": tag,
            }
        )
        .execute()
    )
    dec_id = row.data[0]["id"]
    ref = f"decision:{dec_id}"
    _wire_edges(ref, derived_from, "derives_from", "maya")
    _wire_edges(ref, constrains, "constrains", "maya")
    return f"Logged {display_id} ({ref}): {title}"


@tool
def open_question(title, context: str) -> str:
    """Add an item to the founder's action inbox (a decision with status 'open').

    Use for questions that genuinely need the founder's brain. Returns its ref.
    """
    project_id = _project()
    db = require_admin()
    display_id = _next_display_id("decisions", project_id, "D-", width=3)
    row = (
        db.table("decisions")
        .insert(
            {
                "project_id": project_id,
                "display_id": display_id,
                "decided_by": "maya_autonomous",
                "status": "open",
                "open_type": "escalated",
                "title": title,
                "detail": context,
                "why": "Awaiting founder decision.",
                "tag": "flagged",
            }
        )
        .execute()
    )
    return f"Opened question {display_id} (decision:{row.data[0]['id']}): {title}"


# ── Solutions & features (§6 loop) ─────────────────────────────────────────
@tool
def create_solution(
    title: str,
    summary: str,
    recommended: bool = False,
    derived_from: list[str] | None = None,
) -> str:
    """Record a candidate solution to the validated problem.

    `derived_from`: usually the problem artifact(s) it addresses. Set
    `recommended=True` for the one you'd advise. Returns its ref.
    """
    project_id = _project()
    bad = _missing_refs(derived_from)
    if bad:
        return f"Couldn't create solution — these derived_from refs don't exist: {', '.join(bad)}."
    db = require_admin()
    display_id = _next_display_id("solutions", project_id, "sol-")
    row = (
        db.table("solutions")
        .insert(
            {
                "project_id": project_id,
                "display_id": display_id,
                "title": title,
                "summary": summary,
                "recommended": recommended,
            }
        )
        .execute()
    )
    ref = f"solution:{row.data[0]['id']}"
    _wire_edges(ref, derived_from, "derives_from", "maya")
    return f"Created {display_id} ({ref}): {title}"


@tool
def create_feature(
    title: str,
    description: str,
    in_mvp: bool = False,
    derived_from: list[str] | None = None,
) -> str:
    """Shape a concrete feature from a chosen solution.

    `derived_from`: usually the solution it comes from. `in_mvp` should be left
    False until the explicit MVP-cut decision sets it. Returns its ref.
    """
    project_id = _project()
    bad = _missing_refs(derived_from)
    if bad:
        return f"Couldn't create feature — these derived_from refs don't exist: {', '.join(bad)}."
    db = require_admin()
    display_id = _next_display_id("features", project_id, "f-")
    row = (
        db.table("features")
        .insert(
            {
                "project_id": project_id,
                "display_id": display_id,
                "title": title,
                "description": description,
                "in_mvp": in_mvp,
            }
        )
        .execute()
    )
    ref = f"feature:{row.data[0]['id']}"
    _wire_edges(ref, derived_from, "derives_from", "maya")
    return f"Created {display_id} ({ref}): {title}"


# ── Generic graph + review ─────────────────────────────────────────────────
@tool
def link(dependent: str, depends_on: str, relationship: str, why: str) -> str:
    """Record a dependency edge between two existing nodes.

    `dependent` and `depends_on` are refs ('type:id'). `relationship` is
    'derives_from' | 'constrains' | 'supersedes'. Use when an edge wasn't
    captured at creation. Returns confirmation.
    """
    project_id = _project()
    bad = _missing_refs([dependent, depends_on])
    if bad:
        return f"Couldn't link — these refs don't exist: {', '.join(bad)}."
    dtype, did = _parse_ref(dependent)
    otype, oid = _parse_ref(depends_on)
    depgraph.add_dependency(
        project_id=project_id,
        dependent_type=dtype,
        dependent_id=did,
        depends_on_type=otype,
        depends_on_id=oid,
        relationship=relationship,  # type: ignore[arg-type]
        created_by="maya",
        why=why,
    )
    return f"Linked {dependent} {relationship} {depends_on}"


@tool
def flag_change(node: str, reason: str) -> str:
    """Mark a node as materially changed: bump its version and flag its direct
    dependents for review.

    Use after you edit a node through any path that didn't already propagate.
    `node` is a ref ('type:id'). Returns the dependents now flagged.
    """
    project_id = _project()
    ntype, nid = _parse_ref(node)
    depgraph.bump_version(project_id, ntype, nid)
    flagged = depgraph.mark_dependents_for_review(project_id, ntype, nid, reason)
    if not flagged:
        return f"Marked {node} changed. Nothing depended on it."
    refs = ", ".join(f"{f['type']}:{f['id']}" for f in flagged)
    return f"Marked {node} changed. Flagged for review: {refs}"


@tool
def list_open_reviews() -> str:
    """List every node currently flagged needs_review, with the reason.

    Use to see what a recent change rippled into so you can decide how to act.
    """
    items = depgraph.list_needs_review(_project())
    if not items:
        return "Nothing is flagged for review."
    lines = [f"- {i['type']}:{i['id']} — {i['why']}" for i in items]
    return "Flagged for review:\n" + "\n".join(lines)


@tool
def resolve_review(node: str) -> str:
    """Clear a node's needs_review flag once you've acted on the change.

    `node` is a ref ('type:id'). Returns confirmation.
    """
    project_id = _project()
    ntype, nid = _parse_ref(node)
    depgraph.clear_needs_review(project_id, ntype, nid)
    return f"Cleared review flag on {node}."


# ── Read-back (the DB is your source of truth) ──────────────────────────────
_LIST_READERS = {
    "artifact": artifacts_service.list_discovery,
    "decision": artifacts_service.list_decisions,
    "solution": artifacts_service.list_solutions,
    "feature": artifacts_service.list_features,
}


@tool
def list_nodes(kind: str | None = None) -> str:
    """List your product record straight from the database — your real memory.

    `kind` optionally narrows it to one of: artifact | decision | solution |
    feature. Omit it to see everything. Each line is a 'type:id — title' you can
    copy as a ref into derived_from / link. Read this before referring to or
    wiring something you made earlier; don't rely on recall of past turns.
    """
    project_id = _project()
    if kind is not None and kind not in _LIST_READERS:
        return f"Unknown kind {kind!r}. Use one of: {', '.join(_LIST_READERS)}."
    kinds = [kind] if kind else list(_LIST_READERS)
    lines: list[str] = []
    for k in kinds:
        rows = _LIST_READERS[k](project_id)
        if rows:
            lines.append(f"{k.upper()}S:")
            lines.extend(_fmt_node(k, r) for r in rows)
    if not lines:
        return "Your product record is empty — nothing created yet."
    return "\n".join(lines)


@tool
def get_node(ref: str) -> str:
    """Full detail for one node ('type:id'): its content, version and review
    state, what it was derived from (provenance), and what currently depends on
    it. Read this before you edit, archive, or supersede a node, so you know
    what the change will ripple into.
    """
    project_id = _project()
    ntype, nid = _parse_ref(ref)
    row = _fetch_node(ntype, nid, project_id)
    if not row:
        return f"No such node {ref} in this project."

    parts = [f"{ref}"]
    if row.get("display_id"):
        parts.append(f"display_id: {row['display_id']}")
    parts.append(f"title: {row.get('title') or '(untitled)'}")
    body = row.get("summary") or row.get("detail") or row.get("description")
    if body:
        parts.append(f"content: {body}")
    if row.get("render_kind"):
        parts.append(f"render_kind: {row['render_kind']}")
    if row.get("version"):
        parts.append(f"version: {row['version']}")
    if row.get("needs_review"):
        parts.append(f"NEEDS REVIEW: {row.get('needs_review_why') or '(no reason)'}")

    prov = depgraph.provenance(project_id, ntype, nid)
    if prov:
        parts.append(
            "derived from / constrained by: "
            + ", ".join(
                f"{p['relationship']} {p['depends_on_type']}:{p['depends_on_id']}" for p in prov
            )
        )
    deps = depgraph.direct_dependents(project_id, ntype, nid)
    if deps:
        parts.append(
            "depended on by (would be flagged if this changes): "
            + ", ".join(
                f"{d['dependent_type']}:{d['dependent_id']} ({d['relationship']})" for d in deps
            )
        )
    return "\n".join(parts)


# ── Archive & supersede (soft only — never destroys data) ───────────────────
@tool
def archive_node(ref: str, reason: str) -> str:
    """Retire a node you no longer want — a SOFT hide, never a hard delete.

    It drops off the live surfaces but stays in the database (chat history and
    provenance still resolve). Use when something is wrong, duplicated, or
    obsolete and there's no replacement. If a newer node replaces it, use
    `supersede_node` instead. `reason` is for your own log. Returns confirmation.
    """
    project_id = _project()
    ntype, nid = _parse_ref(ref)
    if not _fetch_node(ntype, nid, project_id):
        return f"No such node {ref} in this project."
    try:
        _soft_hide(ntype, nid, project_id)
    except ValueError as e:
        return str(e)
    return f"Archived {ref}. ({reason})"


@tool
def supersede_node(old_ref: str, new_ref: str, why: str) -> str:
    """Replace one node with a newer one: record that `new_ref` supersedes
    `old_ref`, then soft-hide the old node (it stays in the DB).

    Use when a fresh artifact/decision/solution/feature takes the place of an
    earlier one. Both refs must already exist. Returns confirmation.
    """
    project_id = _project()
    bad = _missing_refs([old_ref, new_ref])
    if bad:
        return f"Couldn't supersede — these refs don't exist: {', '.join(bad)}."
    otype, oid = _parse_ref(old_ref)
    ntype, nid = _parse_ref(new_ref)
    # Edge: the new node supersedes the old one.
    depgraph.add_dependency(
        project_id=project_id,
        dependent_type=ntype,
        dependent_id=nid,
        depends_on_type=otype,
        depends_on_id=oid,
        relationship="supersedes",
        created_by="maya",
        why=why,
    )
    try:
        _soft_hide(otype, oid, project_id)
    except ValueError as e:
        return str(e)
    return f"{new_ref} now supersedes {old_ref}; archived the old one. ({why})"


@tool
def gather_context(anchors: list[str]) -> str:
    """Assemble a briefing pack to hand a specialist before you delegate.

    A specialist is forgetful — it sees only the task you write, nothing else.
    So before delegating a synthesis job (especially Nora's PRD, Kai's sprint, or
    Wes's guardrails), call this with the **anchor** cards the job is about (refs
    like 'feature:…', 'decision:…' — many allowed, from any step). It follows the
    dependency trail back to the roots and returns a ready-to-paste block: the
    anchors in full plus where they came from, summarised.

    Then include the returned block in the `task` description you give the
    specialist, so its work is grounded in the real product record — not just
    your one-line brief. Returns the markdown briefing block.
    """
    return context_pack.build_context_pack(_project(), anchors)


@tool
def list_orphans() -> str:
    """List nodes with no 'derived_from' link — work not yet wired into the
    dependency graph. Some are genuine roots (e.g. the first problem artifact);
    others are things you forgot to connect. Review each: `link` it to what it
    came from, or leave it if it's truly a starting point.
    """
    project_id = _project()
    out: list[str] = []
    for ntype, reader in _LIST_READERS.items():
        for row in reader(project_id):
            prov = depgraph.provenance(project_id, ntype, row["id"])
            if not any(p.get("relationship") == "derives_from" for p in prov):
                out.append(_fmt_node(ntype, row))
    if not out:
        return "No orphans — every node is wired to where it came from."
    return "Nodes with no derived_from link (review each):\n" + "\n".join(out)


# All domain tools, ready to hand to the coordinator.
DOMAIN_TOOLS = [
    create_artifact,
    update_artifact,
    log_decision,
    open_question,
    create_solution,
    create_feature,
    link,
    flag_change,
    list_open_reviews,
    resolve_review,
    list_nodes,
    get_node,
    archive_node,
    supersede_node,
    list_orphans,
    gather_context,
]
