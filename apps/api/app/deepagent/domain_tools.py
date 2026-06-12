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

# A task's complexity is a coarse size label only — never a time estimate. The DB
# enforces this set; we mirror it so Maya gets a clean message, not a raw error.
VALID_COMPLEXITY = ("low", "medium", "high")


def _norm_complexity(value):
    """Return a valid complexity label, or None if absent/invalid (so one bad
    label never blocks a whole sprint create)."""
    if value is None:
        return None
    v = str(value).strip().lower()
    return v if v in VALID_COMPLEXITY else None

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
      wireframe_flow — a UX screen flow (greyscale, mid-fidelity mockups). Compose
        each screen from typed BLOCKS — never HTML; the renderer owns the layout,
        so the screens come out clean and consistent. Shape:
          {device: "phone"|"browser"|"extension"|"desktop",
           flow_name?, flow_type?: "onboarding"|"core"|"settings"|"error"|"empty"|"auth"|"other",
           screens: [{
             name,                                  # short screen name
             appBar?: {title?, leading?: "back"|"menu"|"none", trailing?: [str]},
             blocks: [ ...body blocks, top→bottom... ],
             bottomBar?: {kind:"nav", items:[{label, active?}]}        # pinned tab bar
                       | {kind:"actions", buttons:[{label, variant?}]},  # pinned action bar
             notes?, derived_from?
           }],
           transitions?: [{from, to, trigger?}],
           informed_by?: [str]}
        Block types (pick only what the screen needs):
           {type:"heading", text, level?:1|2|3}
           {type:"text", text, tone?:"default"|"muted"}
           {type:"input", label?, placeholder?, kind?:"text"|"password"|"search"|"textarea"}
           {type:"button", label, variant?:"primary"|"secondary", fullWidth?}
           {type:"buttonGroup", layout?:"row"|"stack", buttons:[{label, variant?}]}
           {type:"list", items:[{title, subtitle?, leading?:"avatar"|"icon"|"thumb", trailing?}]}
           {type:"card", title?, body?, chips?:[str]}
           {type:"image", label?, ratio?:"square"|"wide"|"tall"}
           {type:"media", variant?:"image"|"audio"|"video"|"map", label?}
           {type:"chips", items:[str]}
           {type:"metricRow", metrics:[{value, label?}]}
           {type:"field", label, value?}      # read-only key/value row
           {type:"toggleRow", label, on?}
           {type:"segmented", options:[str], active?}
           {type:"hero", kicker?, title, subtitle?, media?}
           {type:"divider"}  {type:"spacer", size?:"sm"|"md"|"lg"}
        Put primary actions in `bottomBar` (kind:"actions"), not as a trailing
        block, so they pin to the bottom. Keep each screen focused — a handful of
        blocks. Only draw screens AFTER the founder has signed off on the flow in
        chat, and make every element trace to a feature + the friction/pain it
        serves (each screen's `derived_from` + the flow's `informed_by`). See the
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
def update_artifact(
    artifact_id: str,
    reason: str,
    title: str | None = None,
    summary: str | None = None,
    render_kind: str | None = None,
    payload: dict | None = None,
) -> str:
    """Edit an existing discovery artifact in place — any of title, summary,
    render_kind, or payload. Treat artifacts as living objects you can revise.

    Only pass the fields you're changing; the rest are left as-is. If you change
    `render_kind` it must be one of the allowed kinds (see create_artifact), and
    `payload` should match the new kind. `reason` explains what changed and shows
    on the review flags.

    After updating, everything that derived from this artifact is flagged
    `needs_review` so the plan stays coherent. Returns the dependents flagged.
    """
    project_id = _project()
    if render_kind is not None and render_kind not in MAYA_RENDER_KINDS:
        return (
            f"Couldn't update — render_kind '{render_kind}' isn't allowed. "
            f"Choose one of: {', '.join(MAYA_RENDER_KINDS)}."
        )
    try:
        da_service.update(
            artifact_id=artifact_id,
            project_id=project_id,
            title=title,
            summary=summary,
            render_kind=render_kind,
            payload=payload,
        )
    except ValueError as e:
        return f"Couldn't update artifact:{artifact_id} — {e}"
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


@tool
def resolve_question(question: str, answer: str) -> str:
    """Close an open question once the founder has decided — marks it settled and
    records their answer on the decision.

    `question` is the ref of an open question ('decision:…' from open_question).
    Use this after `ask_founder` gets you the answer, so the founder's inbox
    clears and the choice becomes part of the record. Anything depending on the
    question is flagged needs_review. Returns confirmation.
    """
    project_id = _project()
    ntype, nid = _parse_ref(question)
    if ntype not in ("decision", "guardrail"):
        return "resolve_question only applies to an open question (a decision ref)."
    row = _fetch_node(ntype, nid, project_id)
    if not row:
        return f"No such question {question} in this project."
    artifacts_service.resolve_decision(nid, answer)
    flagged = depgraph.mark_dependents_for_review(
        project_id, ntype, nid, f"question answered: {answer[:80]}"
    )
    extra = ""
    if flagged:
        extra = " Flagged for review: " + ", ".join(
            f"{f['type']}:{f['id']}" for f in flagged
        )
    return f"Resolved {question} with the founder's answer.{extra}"


@tool
def update_decision(
    decision_id: str,
    reason: str,
    title: str | None = None,
    detail: str | None = None,
    why: str | None = None,
    tag: str | None = None,
) -> str:
    """Edit a decision in place — fix its title, detail, rationale (`why`), or
    `tag` ('scope'|'guardrail'|'technical'|'flagged'). For a genuine change of
    mind where a new decision replaces the old one, use `supersede_node` instead;
    use this for clarifications and corrections.

    Only pass the fields you're changing. `reason` shows on review flags;
    dependents are flagged needs_review. Returns what got flagged.
    """
    return _apply_node_update(
        "decision",
        decision_id,
        {"title": title, "detail": detail, "why": why, "tag": tag},
        reason,
    )


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


def _apply_node_update(
    node_type: str, node_id: str, payload: dict, reason: str
) -> str:
    """Patch a node's own columns in place, then run the coherence ripple.

    Shared by update_solution / update_feature / update_decision: writes the
    given columns, bumps the version, and flags direct dependents needs_review so
    the plan stays coherent. Returns a message naming what got flagged.
    """
    project_id = _project()
    if not depgraph.node_exists(project_id, node_type, node_id):
        return f"No such {node_type}:{node_id} in this project."
    payload = {k: v for k, v in payload.items() if v is not None}
    if not payload:
        return "Nothing to update — pass at least one field to change."
    db = require_admin()
    (
        db.table(depgraph.NODE_TABLES[node_type])
        .update(payload)
        .eq("id", node_id)
        .eq("project_id", project_id)
        .execute()
    )
    depgraph.bump_version(project_id, node_type, node_id)
    flagged = depgraph.mark_dependents_for_review(project_id, node_type, node_id, reason)
    if not flagged:
        return f"Updated {node_type}:{node_id}. Nothing depended on it."
    refs = ", ".join(f"{f['type']}:{f['id']}" for f in flagged)
    return f"Updated {node_type}:{node_id}. Flagged for review: {refs}"


@tool
def update_solution(
    solution_id: str,
    reason: str,
    recommended: bool | None = None,
    title: str | None = None,
    summary: str | None = None,
) -> str:
    """Edit a candidate solution in place — flip `recommended` after you've formed
    a view, or fix its title/summary. Treat solutions as living objects.

    Only pass the fields you're changing. `reason` shows on review flags. After
    updating, anything derived from this solution (its features) is flagged
    needs_review. Returns what got flagged.
    """
    return _apply_node_update(
        "solution",
        solution_id,
        {"recommended": recommended, "title": title, "summary": summary},
        reason,
    )


@tool
def update_feature(
    feature_id: str,
    reason: str,
    in_mvp: bool | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: int | None = None,
) -> str:
    """Edit a feature in place. This is how the **MVP cut** actually takes effect:
    set `in_mvp=True` on each feature that makes the cut (and `in_mvp=False` to
    drop one back out). It's also how you fix a feature's title/description/priority.

    The PRD's "what we're building" list is the set of in-MVP features, so this is
    what populates it. Only pass the fields you're changing. `reason` shows on
    review flags; dependents (screens, PRD sections, tasks) are flagged
    needs_review so scope stays coherent. Returns what got flagged.
    """
    return _apply_node_update(
        "feature",
        feature_id,
        {"in_mvp": in_mvp, "title": title, "description": description, "priority": priority},
        reason,
    )


# ── PRD + Sprint (the buildable deliverables) ──────────────────────────────
@tool
def write_prd(body_md: str) -> str:
    """Save the PRD — the spec document — so it lands on the PRD tab.

    `body_md` is the full PRD as markdown; use `## ` headings for each section
    (the tab renders them as a navigable outline). Call this AFTER Nora drafts
    the PRD — her draft is just text in chat until you persist it here. The MVP
    feature list and the guardrails are added around your body automatically.
    Re-calling replaces the PRD and bumps its version.
    """
    project_id = _project()
    if not body_md or not body_md.strip():
        return "Couldn't save PRD — the body is empty."
    row = artifacts_service.upsert_prd(project_id, body_md)
    return f"PRD saved (v{row.get('version', '?')}). It now shows on the PRD tab."


@tool
def create_sprint(name: str, tasks: list[dict], subtitle: str | None = None) -> str:
    """Save the sprint board so the founder's coding agent can pick it up. Call
    this AFTER Kai plans the sprint — his plan is just chat text until you persist
    it here.

    Each task is a small **vertical slice** the coding agent can build AND verify
    end-to-end on its own — it works from a fixed context window and is blind to
    everything you leave out, so make each task self-contained and intent-level
    (the WHAT and WHY, never the HOW — no tech stack, file paths, or code design;
    the agent decides those or reads them from the repo).

    `tasks` is a list of task objects, each:
      {"title": str (required),
       "goal": str,             # the outcome, in one line
       "why": str,              # the user problem it solves → put in "description"
       "description": str,      # the intent / user problem (not implementation)
       "acceptance": [str],     # testable "done" conditions — the #1 quality lever
       "verification": [str],   # how we'll know it works, in plain language
       "do_not": [str],         # non-goals / what this task must NOT do or touch
       "blocked_by": [str],     # display_ids of tasks that must finish first (T-1, …)
       "prd_context": str,      # which feature / PRD section / guardrail it serves
       "prompt_brief": str,     # the self-contained brief the coding agent acts on
       "complexity": str}       # coarse size: "low" | "medium" | "high" (never a time estimate)
    Tasks are numbered T-1, T-2, … in the order given; order them **bottom-up** so
    no-dependency slices come first. `blocked_by` references those ids. Guardrails
    aren't copied onto each task — the agent inherits them from the decisions.

    This starts a NEW sprint each call. To change a sprint that already exists —
    add, edit, or drop tasks, or rename it — use add_task / update_task /
    remove_task / update_sprint instead, so you amend the live board rather than
    spawning a duplicate. Returns the sprint + task count.
    """
    project_id = _project()
    if not tasks:
        return "Couldn't create the sprint — no tasks were given."
    number = len(artifacts_service.list_sprints(project_id)) + 1
    sprint = artifacts_service.create_sprint(
        project_id=project_id, number=number, name=name, subtitle=subtitle
    )
    sprint_id = sprint.get("id")
    if not sprint_id:
        return "Couldn't create the sprint — the board insert failed."
    created = 0
    for i, t in enumerate(tasks, start=1):
        if not isinstance(t, dict):
            continue
        title = (t.get("title") or "").strip()
        if not title:
            continue
        artifacts_service.create_task(
            project_id=project_id,
            sprint_id=sprint_id,
            display_id=f"T-{i}",
            title=title,
            goal=t.get("goal"),
            description=t.get("description"),
            acceptance=t.get("acceptance") if isinstance(t.get("acceptance"), list) else None,
            verification=t.get("verification") if isinstance(t.get("verification"), list) else None,
            do_not=t.get("do_not") if isinstance(t.get("do_not"), list) else None,
            prd_context=t.get("prd_context"),
            blocked_by=t.get("blocked_by") if isinstance(t.get("blocked_by"), list) else None,
            prompt_brief=t.get("prompt_brief"),
            complexity=_norm_complexity(t.get("complexity")),
        )
        created += 1
    return f"Created sprint '{name}' with {created} task(s). It now shows on the Sprint tab."


@tool
def update_task(
    task_id: str,
    status: str | None = None,
    note: str | None = None,
    title: str | None = None,
    goal: str | None = None,
    description: str | None = None,
    acceptance: list[str] | None = None,
    verification: list[str] | None = None,
    do_not: list[str] | None = None,
    prd_context: str | None = None,
    blocked_by: list[str] | None = None,
    prompt_brief: str | None = None,
    complexity: str | None = None,
) -> str:
    """Edit a task on the board in place — its `status` ('todo' | 'in_progress' |
    'done'), or its content (title, goal, description, acceptance, verification,
    do_not, prd_context, blocked_by, prompt_brief, complexity), and optionally a
    `note`. `complexity` is a coarse size — one of 'low' | 'medium' | 'high'
    (never a time estimate). The founder's coding agent normally moves status over
    MCP as it builds; use this to amend the plan yourself without recreating the
    sprint. Only pass fields you're changing.
    """
    if complexity is not None and str(complexity).strip().lower() not in VALID_COMPLEXITY:
        return (
            f"Couldn't update — complexity '{complexity}' isn't allowed. "
            f"Use one of: {', '.join(VALID_COMPLEXITY)}."
        )
    if complexity is not None:
        complexity = str(complexity).strip().lower()
    updated = artifacts_service.patch_task(
        task_id,
        status=status,
        agent_note=note,
        title=title,
        goal=goal,
        description=description,
        acceptance=acceptance,
        verification=verification,
        do_not=do_not,
        prd_context=prd_context,
        blocked_by=blocked_by,
        prompt_brief=prompt_brief,
        complexity=complexity,
    )
    if not updated:
        return f"Nothing to update on task {task_id} — pass at least one field."
    return f"Updated task {task_id}."


@tool
def add_task(
    title: str,
    goal: str | None = None,
    description: str | None = None,
    acceptance: list[str] | None = None,
    verification: list[str] | None = None,
    do_not: list[str] | None = None,
    prd_context: str | None = None,
    blocked_by: list[str] | None = None,
    prompt_brief: str | None = None,
    complexity: str | None = None,
) -> str:
    """Add a single task to the CURRENT (active) sprint — amend the live board
    instead of recreating it. Same fields as one item in create_sprint's list
    (keep it an intent-level vertical slice). It's numbered T-N after the
    sprint's existing tasks. Use create_sprint only to start a new sprint.
    """
    project_id = _project()
    title = (title or "").strip()
    if not title:
        return "Couldn't add task — a title is required."
    sprint = artifacts_service.get_active_sprint(project_id)
    if not sprint:
        return "No active sprint yet — use create_sprint to start the board first."
    sprint_id = sprint["id"]
    existing = [
        t for t in artifacts_service.list_tasks(project_id) if t.get("sprint_id") == sprint_id
    ]
    n = len(existing) + 1
    artifacts_service.create_task(
        project_id=project_id,
        sprint_id=sprint_id,
        display_id=f"T-{n}",
        title=title,
        goal=goal,
        description=description,
        acceptance=acceptance,
        verification=verification,
        do_not=do_not,
        prd_context=prd_context,
        blocked_by=blocked_by,
        prompt_brief=prompt_brief,
        complexity=_norm_complexity(complexity),
    )
    return f"Added T-{n} '{title}' to sprint '{sprint.get('name')}'."


@tool
def remove_task(task_id: str, reason: str) -> str:
    """Take a task off the board — a SOFT hide (it stays in the DB), never a hard
    delete. Use when a planned task is no longer needed. `reason` is for your log.
    """
    project_id = _project()
    if not depgraph.node_exists(project_id, "task", task_id):
        return f"No such task:{task_id} in this project."
    artifacts_service.delete_task(task_id, project_id)
    return f"Removed task {task_id} from the board. ({reason})"


@tool
def update_sprint(
    name: str | None = None,
    subtitle: str | None = None,
    status: str | None = None,
) -> str:
    """Amend the CURRENT (active) sprint's own details — its name, subtitle, or
    status ('active' | 'done'). To change the tasks on it use add_task /
    update_task / remove_task; to start a fresh sprint use create_sprint.
    """
    project_id = _project()
    sprint = artifacts_service.get_active_sprint(project_id)
    if not sprint:
        return "No active sprint to update."
    if name is None and subtitle is None and status is None:
        return "Nothing to update — pass a name, subtitle, or status."
    artifacts_service.update_sprint(
        sprint["id"], name=name, subtitle=subtitle, status=status
    )
    return f"Updated sprint '{name or sprint.get('name')}'."


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
    "task": artifacts_service.list_tasks,
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
    So before delegating a synthesis job (especially Nora's PRD or Kai's sprint),
    call this with the **anchor** cards the job is about (refs
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
    resolve_question,
    update_decision,
    create_solution,
    update_solution,
    create_feature,
    update_feature,
    write_prd,
    create_sprint,
    update_task,
    add_task,
    remove_task,
    update_sprint,
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
