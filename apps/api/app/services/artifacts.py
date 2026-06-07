"""DB writes for the four canonical artifacts: PRD, sprint, decisions, guardrails."""
from __future__ import annotations

import re as _re
from typing import Optional

from app.db import require_admin


# ─── PRD ────────────────────────────────────────────────────────────────────

def get_active_prd(project_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("prds")
        .select("*")
        .eq("project_id", project_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    return (row.data or [None])[0]


def upsert_prd(project_id: str, body_md: str) -> dict:
    """Legacy full-body upsert. Bumps version. Use upsert_prd_full for the
    section-aware path (writes prd_sections rows too)."""
    db = require_admin()
    current = get_active_prd(project_id)
    next_version = ((current or {}).get("version") or 0) + 1
    row = db.table("prds").insert({
        "project_id": project_id,
        "version": next_version,
        "status": "draft",
        "body_md": body_md,
    }).execute()
    return row.data[0] if row.data else {}


# ── Section helpers ────────────────────────────────────────────────────

def _slug(s: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "section"


# ── Section-id resolution ──────────────────────────────────────────────
# Maya (and Nora downstream) frequently pick slightly different slugs for
# the same conceptual section across turns — "tech", "tech-stack",
# "what-were-building-it-with" all referring to the same thing. Left
# unchecked, this fans out into ghost sections.
#
# We collapse the drift by token-set matching: two slugs match if they
# share enough non-trivial tokens, OR if one slug's tokens are mostly
# a subset of the other's. This avoids needing an external dep
# (Levenshtein, rapidfuzz) and is good enough for the short tag-style
# strings we're dealing with.

# Tokens that don't carry meaning when matching ("the", "of", etc.)
_STOP_TOKENS = {"the", "a", "an", "of", "for", "to", "and", "or", "with", "we", "re", "in", "on", "at", "by"}


def _section_tokens(section_id: str) -> set[str]:
    raw = _re.split(r"[^a-z0-9]+", (section_id or "").lower())
    return {t for t in raw if t and t not in _STOP_TOKENS}


def tokens_overlap(a: str, b: str) -> float:
    """Jaccard token overlap on two strings, using the same stop-token set
    as section_id resolution. Returns 0..1. Used by Wes-dedup and any
    other similarity check that operates on short imperative strings."""
    ta = _section_tokens(a)
    tb = _section_tokens(b)
    if not ta or not tb:
        return 0.0
    if ta <= tb or tb <= ta:
        return 1.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union) if union else 0.0


def resolve_section_id(
    requested_id: str,
    existing_sections: list[dict],
    *,
    min_overlap: float = 0.5,
) -> Optional[str]:
    """Return the existing section_id that `requested_id` should merge into,
    or None if it's genuinely new.

    Matching strategy (cheap, dependency-free):
      1. Exact slug match → return it.
      2. Token-set overlap ≥ min_overlap (Jaccard over non-stop tokens) →
         return the best-overlapping existing slug.
      3. One slug's tokens fully contained in the other → return existing.

    Tuned for short tag-style strings (2-5 tokens). We bias toward reuse:
    when in doubt, merge — the cost of a wrong merge is one bad section
    edit; the cost of drift is unbounded ghost sections.
    """
    if not requested_id or not existing_sections:
        return None
    # 1. Exact match — return as-is.
    for s in existing_sections:
        if s.get("section_id") == requested_id:
            return requested_id

    req_tokens = _section_tokens(requested_id)
    if not req_tokens:
        return None

    best_id: Optional[str] = None
    best_score = 0.0
    for s in existing_sections:
        sid = s.get("section_id") or ""
        ex_tokens = _section_tokens(sid)
        if not ex_tokens:
            continue
        # Containment (one fully contained in the other) → strong signal.
        if req_tokens <= ex_tokens or ex_tokens <= req_tokens:
            score = 1.0
        else:
            inter = req_tokens & ex_tokens
            union = req_tokens | ex_tokens
            score = len(inter) / len(union) if union else 0.0
        if score >= min_overlap and score > best_score:
            best_id = sid
            best_score = score
    return best_id


def parse_sections(body_md: str) -> list[dict]:
    """Split a PRD body by `## ` headings into ordered section dicts."""
    if not body_md:
        return []
    sections: list[dict] = []
    current: dict | None = None
    body_lines: list[str] = []
    for line in body_md.split("\n"):
        m = _re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current is not None:
                current["body_md"] = "\n".join(body_lines).strip()
                sections.append(current)
            current = {
                "section_id": _slug(m.group(1)),
                "title": m.group(1),
                "order_index": len(sections),
            }
            body_lines = []
        elif current is not None:
            body_lines.append(line)
    if current is not None:
        current["body_md"] = "\n".join(body_lines).strip()
        sections.append(current)
    return sections


def list_prd_sections(prd_id: str) -> list[dict]:
    db = require_admin()
    rows = (
        db.table("prd_sections")
        .select("*")
        .eq("prd_id", prd_id)
        .order("order_index")
        .execute()
    )
    return rows.data or []


def get_prd_sections(prd_id: str) -> list[dict]:
    """Backwards-compat alias for list_prd_sections."""
    return list_prd_sections(prd_id)


def upsert_prd_section_row(prd_id: str, section_id: str, title: str, body_md: str, order_index: int) -> dict:
    db = require_admin()
    row = db.table("prd_sections").upsert({
        "prd_id": prd_id,
        "section_id": section_id,
        "title": title,
        "body_md": body_md,
        "order_index": order_index,
    }, on_conflict="prd_id,section_id").execute()
    return row.data[0] if row.data else {}


# ── PRD body assembly ────────────────────────────────────────────────
# Guardrails used to be appended to the PRD body as a §Guardrails section.
# We removed that in Phase 11: guardrails now live exclusively in their own
# dashboard tab + are surfaced by the MCP `get_session_context` as a
# separate top-level field. Two reasons to keep them out of the PRD body:
#   1. Duplicate surface — founders saw the same guardrail twice (PRD body
#      + Guardrails tab) and didn't know which was canonical.
#   2. PRD versioning was getting polluted: a new guardrail bumped the PRD
#      version even though no PRD section had changed.
# `assemble_prd(project_id, body_md)` exists for symmetry and future use
# (e.g. injecting a header), but right now it's a no-op pass-through.

def assemble_prd(project_id: str, base_body_md: str) -> str:
    """Return the PRD body as it should be stored. Currently a pass-through;
    the indirection lets us inject derived content later without re-wiring
    every caller."""
    return base_body_md


# Back-compat alias — any external scripts importing the old name keep
# working. Returns the body unchanged (the guardrails-injection behaviour
# is gone; see the comment above for why).
def assemble_prd_with_guardrails(project_id: str, base_body_md: str) -> str:  # noqa: ARG001
    return assemble_prd(project_id, base_body_md)


# ── Versioned writes ──────────────────────────────────────────────────

def upsert_prd_full(
    *,
    project_id: str,
    body_md: str,
    sections: list[dict],
    change_kind: str = "full",
    change_reason: str = "full draft",
) -> dict:
    """Insert a new PRD version + write the section rows. Old versions kept."""
    db = require_admin()
    existing = (
        db.table("prds")
        .select("version")
        .eq("project_id", project_id)
        .order("version", desc=True)
        .limit(1)
        .execute()
    )
    next_version = (existing.data[0]["version"] + 1) if existing.data else 1
    row = db.table("prds").insert({
        "project_id": project_id,
        "version": next_version,
        "status": "draft",
        "body_md": body_md,
    }).execute()
    prd = row.data[0] if row.data else {}
    if prd.get("id"):
        for s in sections:
            db.table("prd_sections").insert({
                "prd_id": prd["id"],
                "section_id": s["section_id"],
                "title": s["title"],
                "body_md": s["body_md"],
                "order_index": s["order_index"],
            }).execute()
    return prd


def update_prd_section(
    *,
    project_id: str,
    section_id: str,
    title: str,
    body_md: str,
    order_index: int,
    change_summary: str,
    before: str | None = None,
) -> dict:
    """Apply a section-level update. Creates a new prd version with the diff
    applied; previous versions' sections stay intact."""
    current = get_active_prd(project_id)
    if not current:
        raise ValueError("No active PRD to update")
    prev_sections = list_prd_sections(current["id"])
    new_sections: list[dict] = []
    found = False
    for s in prev_sections:
        if s["section_id"] == section_id:
            new_sections.append({
                "section_id": section_id,
                "title": title,
                "body_md": body_md,
                "order_index": s["order_index"],
            })
            found = True
        else:
            new_sections.append({
                "section_id": s["section_id"],
                "title": s["title"],
                "body_md": s["body_md"],
                "order_index": s["order_index"],
            })
    if not found:
        new_sections.append({
            "section_id": section_id,
            "title": title,
            "body_md": body_md,
            "order_index": order_index,
        })

    base_body = "\n\n".join(
        f"## {s['title']}\n\n{s['body_md']}".rstrip() for s in new_sections
    ).strip()
    full_body = assemble_prd(project_id, base_body)

    return upsert_prd_full(
        project_id=project_id,
        body_md=full_body,
        sections=new_sections,
        change_kind="section_update",
        change_reason=f"{section_id}: {change_summary}",
    )


# ─── Sprints + tasks ────────────────────────────────────────────────────────

def create_sprint(
    project_id: str,
    number: int,
    name: str,
    subtitle: Optional[str] = None,
    tech_stack: Optional[dict] = None,
    data_models: Optional[list] = None,
    repo_layout: Optional[str] = None,
    conventions: Optional[dict] = None,
    existing_files: Optional[list] = None,
) -> dict:
    db = require_admin()
    row = db.table("sprints").insert({
        "project_id": project_id,
        "number": number,
        "name": name,
        "subtitle": subtitle,
        "status": "active",
        "tech_stack": tech_stack or {},
        "data_models": data_models or [],
        "repo_layout": repo_layout,
        "conventions": conventions or {},
        "existing_files": existing_files or [],
    }).execute()
    return row.data[0] if row.data else {}


def update_project_macro(project_id: str, project_brief: Optional[str], north_star: Optional[str]) -> dict:
    """Set the project-level brief + north_star (the macro context the coding
    agent reads at every session start)."""
    db = require_admin()
    payload: dict = {}
    if project_brief is not None:
        payload["project_brief"] = project_brief
    if north_star is not None:
        payload["north_star"] = north_star
    if not payload:
        return {}
    row = db.table("projects").update(payload).eq("id", project_id).execute()
    return row.data[0] if row.data else {}


def list_sprints(project_id: str) -> list[dict]:
    db = require_admin()
    rows = (
        db.table("sprints")
        .select("*")
        .eq("project_id", project_id)
        .order("number")
        .execute()
    )
    return rows.data or []


def create_task(
    *,
    project_id: str,
    sprint_id: str,
    display_id: str,
    title: str,
    goal: Optional[str] = None,
    description: Optional[str] = None,
    acceptance: Optional[list] = None,
    prd_context: Optional[str] = None,
    do_not: Optional[list] = None,
    blocked_by: Optional[list] = None,
    # Enriched coding-agent fields
    tech_decisions: Optional[dict] = None,
    data_contracts: Optional[list] = None,
    verification: Optional[list] = None,
    pitfalls: Optional[list] = None,
    complexity: Optional[str] = None,
    secrets_required: Optional[list] = None,
    secrets_setup: Optional[list] = None,
    refs: Optional[list] = None,
    prompt_brief: Optional[str] = None,
) -> dict:
    db = require_admin()
    row = db.table("tasks").insert({
        "project_id": project_id,
        "sprint_id": sprint_id,
        "display_id": display_id,
        "status": "todo",
        "title": title,
        "goal": goal,
        "description": description,
        "acceptance": acceptance or [],
        "prd_context": prd_context,
        "do_not": do_not or [],
        "blocked_by": blocked_by or [],
        "tech_decisions": tech_decisions or {},
        "data_contracts": data_contracts or [],
        "verification": verification or [],
        "pitfalls": pitfalls or [],
        "complexity": complexity,
        "secrets_required": secrets_required or [],
        "secrets_setup": secrets_setup or [],
        "refs": refs or [],
        "prompt_brief": prompt_brief,
    }).execute()
    return row.data[0] if row.data else {}


def list_tasks(project_id: str, status: Optional[str] = None) -> list[dict]:
    db = require_admin()
    q = db.table("tasks").select("*").eq("project_id", project_id)
    if status:
        q = q.eq("status", status)
    rows = q.order("display_id").execute()
    return rows.data or []


def get_task(task_id: str) -> Optional[dict]:
    db = require_admin()
    row = db.table("tasks").select("*").eq("id", task_id).maybe_single().execute()
    return row.data if row else None


def update_task_status(task_id: str, status: str, agent_note: Optional[str] = None) -> dict:
    db = require_admin()
    payload: dict = {"status": status}
    if agent_note:
        payload["agent_note"] = agent_note
    row = db.table("tasks").update(payload).eq("id", task_id).execute()
    return row.data[0] if row.data else {}


def complete_task(task_id: str, summary: str, files_touched: list[str]) -> dict:
    db = require_admin()
    row = db.table("tasks").update({
        "status": "done",
        "completion_summary": summary,
        "files_touched": files_touched,
    }).eq("id", task_id).execute()
    return row.data[0] if row.data else {}


# ─── Decisions ──────────────────────────────────────────────────────────────

def _next_decision_display_id(project_id: str) -> str:
    db = require_admin()
    rows = (
        db.table("decisions")
        .select("display_id")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not rows.data:
        return "D-001"
    last = rows.data[0]["display_id"]  # 'D-014'
    try:
        n = int(last.split("-")[1])
    except Exception:
        n = 0
    return f"D-{n+1:03d}"


def log_decision(
    *,
    project_id: str,
    decided_by: str,    # 'maya_autonomous' | 'agent_with_user' | 'maya_with_user' | 'user' | 'agent_flagged'
    title: str,
    detail: str,
    why: str,
    related_task_id: Optional[str] = None,
    tag: Optional[str] = None,
    affects: Optional[list] = None,
    status: str = "decided",
    open_type: Optional[str] = None,
    supersedes: Optional[str] = None,
) -> dict:
    """Insert a decision. If `supersedes` is set, that prior decision is
    stamped superseded_at + superseded_by in the same transaction (best-effort
    — Supabase REST doesn't expose multi-statement TXs, so we do it as two
    writes with the new row written first so we always have an authoritative
    'replaced by' pointer)."""
    db = require_admin()
    payload = {
        "project_id": project_id,
        "display_id": _next_decision_display_id(project_id),
        "decided_by": decided_by,
        "status": status,
        "open_type": open_type,
        "title": title,
        "detail": detail,
        "why": why,
        "related_task_id": related_task_id,
        "tag": tag,
        "affects": affects or [],
    }
    # Only include the supersession key when set — this keeps inserts
    # working against schemas that haven't applied migration
    # 20260516_000003 yet (Supabase REST validates payload keys against
    # its schema cache; sending an unknown column hard-fails the whole
    # insert). The dashboard / MCP query side is unaffected.
    if supersedes:
        payload["supersedes"] = supersedes
    row = db.table("decisions").insert(payload).execute()
    new_row = row.data[0] if row.data else {}

    if supersedes and new_row.get("id"):
        # Stamp the old row so dashboards / MCP filter it out by default.
        # We don't refuse if the prior row is already superseded — chains
        # of "Tavily → Firecrawl → Exa" should all collapse to the latest.
        from datetime import datetime, timezone
        try:
            db.table("decisions").update({
                "superseded_at": datetime.now(timezone.utc).isoformat(),
                "superseded_by": new_row["id"],
            }).eq("id", supersedes).eq("project_id", project_id).execute()
        except Exception:
            # If the migration isn't applied, the stamp fails silently —
            # the new decision still landed; manual supersession can be
            # done in the dashboard later. Don't fail the insert path.
            pass

    return new_row


def list_decisions(
    project_id: str,
    status: Optional[str] = None,
    include_superseded: bool = False,
) -> list[dict]:
    """Live decisions by default. Pass `include_superseded=True` to see the
    full history (audit / 'show superseded' toggle in the UI).

    Graceful-degrade when the supersession migration hasn't been applied:
    we try the filtered query first, fall back to unfiltered if the column
    doesn't exist. Keeps the app functional during migration rollouts.
    """
    db = require_admin()
    def _build_query(filter_superseded: bool):
        q = db.table("decisions").select("*").eq("project_id", project_id)
        if status:
            q = q.eq("status", status)
        if filter_superseded:
            q = q.is_("superseded_at", "null")
        return q.order("created_at", desc=True)

    try:
        rows = _build_query(filter_superseded=not include_superseded).execute()
        return rows.data or []
    except Exception as e:
        # 42703 = undefined_column. Fall through to unfiltered for any
        # exception so a transient REST glitch doesn't black-hole the
        # dashboard — superseded rows are rare in practice.
        if "superseded_at" in str(e) or "42703" in str(e):
            rows = _build_query(filter_superseded=False).execute()
            return rows.data or []
        raise


def resolve_decision(decision_id: str, detail_appendix: Optional[str] = None) -> dict:
    db = require_admin()
    payload: dict = {"status": "decided"}
    if detail_appendix:
        existing = db.table("decisions").select("detail").eq("id", decision_id).maybe_single().execute()
        if existing and existing.data:
            payload["detail"] = (existing.data["detail"] or "") + "\n\n" + detail_appendix
    row = db.table("decisions").update(payload).eq("id", decision_id).execute()
    return row.data[0] if row.data else {}


# ─── Discovery artifacts (Maya-curated dashboard cards) ────────────────────
# Full CRUD lives in services/discovery_artifacts.py. This thin helper exists
# for legacy callers that want a flat list without going through the full
# discovery_artifacts module. Renamed from `list_research` for vocab parity.

def list_discovery(project_id: str) -> list[dict]:
    """Return live (non-deleted) discovery artifacts for the dashboard."""
    db = require_admin()
    rows = (
        db.table("discovery_artifacts")
        .select("*")
        .eq("project_id", project_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data or []


# Back-compat alias so any straggler import keeps working until cleaned up.
list_research = list_discovery


# ─── Solutions & features (deepagent §6 product-arc loop) ──────────────────
# These are the convergence nodes Maya produces between discovery and the PRD:
# candidate solutions to the validated problem, then the concrete features
# shaped from the chosen solution(s). The MVP cut is a decision (tag='scope')
# that constrains the features it keeps — `in_mvp` reflects that cut.

def list_solutions(project_id: str) -> list[dict]:
    """Live (non-archived) candidate solutions, recommended-first then newest."""
    db = require_admin()
    rows = (
        db.table("solutions")
        .select("*")
        .eq("project_id", project_id)
        .is_("deleted_at", "null")
        .order("recommended", desc=True)
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data or []


def list_features(project_id: str) -> list[dict]:
    """Live (non-archived) features. MVP first, then by priority (nulls last)."""
    db = require_admin()
    rows = (
        db.table("features")
        .select("*")
        .eq("project_id", project_id)
        .is_("deleted_at", "null")
        .order("in_mvp", desc=True)
        .order("priority", desc=False)
        .order("created_at", desc=False)
        .execute()
    )
    return rows.data or []


# ─── Review surface (lazy dirty-marking, deepagent §8) ─────────────────────
# Every node table carries needs_review / needs_review_why. The depgraph
# engine flags direct dependents when an upstream node changes. This wrapper
# enriches the flat {type,id,why} list with each node's human title so the
# dashboard can render a readable "needs another look" surface.

# node type -> (table, title-bearing column). prd_sections uses `title`;
# decisions/solutions/features use `title`; tasks use `title`; discovery
# artifacts use `title`. We select id+title+display_id where present.
_REVIEW_TITLE_COL: dict[str, str] = {
    "artifact": "title",
    "decision": "title",
    "guardrail": "title",
    "task": "title",
    "prd_section": "title",
    "solution": "title",
    "feature": "title",
}


def list_reviews(project_id: str) -> list[dict]:
    """Flagged nodes enriched with title + display_id for the review surface.

    Returns rows shaped `{type, id, why, title, display_id}`. Titles are
    fetched per node from its physical table; a node whose row vanished
    (rare race) is returned with an empty title rather than dropped.
    """
    from app.deepagent import depgraph

    flagged = depgraph.list_needs_review(project_id)
    if not flagged:
        return []
    db = require_admin()
    out: list[dict] = []
    for item in flagged:
        ntype = item.get("type")
        nid = item.get("id")
        table = depgraph.NODE_TABLES.get(ntype or "")
        title = ""
        display_id = None
        if table and nid:
            try:
                sel = "title"
                # decisions/solutions/features/tasks carry a display_id
                if table in ("decisions", "solutions", "features", "tasks"):
                    sel = "title,display_id"
                row = (
                    db.table(table)
                    .select(sel)
                    .eq("id", nid)
                    .maybe_single()
                    .execute()
                )
                data = (row.data if row else None) or {}
                title = data.get("title") or ""
                display_id = data.get("display_id")
            except Exception:
                pass
        out.append({
            "type": ntype,
            "id": nid,
            "why": item.get("why"),
            "title": title,
            "display_id": display_id,
        })
    return out
