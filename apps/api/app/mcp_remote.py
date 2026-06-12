"""Hosted MCP endpoint — the founder's coding agent connects HERE.

Mounted at /mcp on the main API service (see main.py), so connecting an agent
needs zero local install: the founder pastes one snippet and the agent talks
Streamable HTTP straight to this endpoint with its `ps_live_…` key in a header.

Auth: every request must carry the project key (X-PS-Key, or Authorization:
Bearer). The ASGI wrapper validates it via services.mcp_keys (which also stamps
last_seen_at — powering the "agent connected" dot in the UI) and binds the
project id to a contextvar the tools read. The key IS the project scope: an
agent can never see or touch another project.

Tools call the service layer in-process (no HTTP hop). Division of labor is
enforced in the tool surface itself: the agent can read everything, move and
complete tasks, log decisions, ask Maya for clarification, and ADD tasks it
discovers mid-build (auto-flagged for Maya's review) — but it cannot create
sprints. When a sprint is done it calls `request_next_sprint` with a build
report; Maya plans the next one grounded in the full product record.
"""
from __future__ import annotations

import asyncio
import contextvars
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from app.db import require_admin
from app.services import artifacts as art_svc
from app.services import mcp_keys as keys_svc

# Bound per-request by the auth wrapper below.
_project_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_remote_project_id", default=None
)


def _project() -> str:
    pid = _project_ctx.get()
    if not pid:
        raise RuntimeError("No authenticated project bound to this MCP request.")
    return pid


# Stateless + JSON responses: each call stands alone (no server-side session
# state to lose on Cloud Run scale-to-zero), and plain JSON keeps every client
# (and curl) happy. `streamable_http_path="/"` so the mount point IS the endpoint.
server = FastMCP(
    "productsense",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


def _err(text: str) -> dict:
    """Tool-execution error (not a protocol error) so the agent can self-correct."""
    return {"isError": True, "content": [{"type": "text", "text": text}]}


def _get_project_row(project_id: str) -> dict:
    row = (
        require_admin()
        .table("projects")
        .select("*")
        .eq("id", project_id)
        .maybe_single()
        .execute()
    )
    return (row.data if row else None) or {}


def _resolve_task(task_id: str, project_id: str) -> Optional[dict]:
    """Accept a UUID or a display_id (T-1 / t1). Return the task row or None."""
    tasks = art_svc.list_tasks(project_id)
    norm = (task_id or "").strip().lower()
    for t in tasks:
        if t["id"] == task_id or (t.get("display_id") or "").lower() == norm:
            return t
    return None


# ─── Read tools ──────────────────────────────────────────────────────────


@server.tool()
async def get_session_context() -> dict:
    """Everything you need to resume work, in ONE call: the project brief and
    north star, the active sprint, your current + next unblocked tasks,
    recent decisions, the guardrails you must respect, and a PRD summary.
    Read this first at the start of every session."""
    pid = _project()
    project = _get_project_row(pid)
    tasks = art_svc.list_tasks(pid)
    decisions = art_svc.list_decisions(pid)
    prd = art_svc.get_active_prd(pid)
    sprint = art_svc.get_active_sprint(pid)

    in_progress = [t for t in tasks if t["status"] == "in_progress"]
    next_unblocked = [t for t in tasks if t["status"] == "todo" and not t.get("blocked_by")]
    guardrails = [d for d in decisions if d.get("tag") == "guardrail"]

    secrets_required: list[str] = []
    secrets_setup_by_name: dict[str, dict] = {}
    for t in tasks:
        if t.get("status") == "done":
            continue
        for s in (t.get("secrets_required") or []):
            if s and s not in secrets_required:
                secrets_required.append(s)
        for entry in (t.get("secrets_setup") or []):
            if isinstance(entry, dict) and entry.get("name") and entry["name"] not in secrets_setup_by_name:
                secrets_setup_by_name[entry["name"]] = entry

    return {
        "project_id": pid,
        "project_brief": project.get("project_brief"),
        "north_star": project.get("north_star"),
        "sprint": {
            "name": sprint.get("name") if sprint else None,
            "subtitle": sprint.get("subtitle") if sprint else None,
            "tech_stack": (sprint or {}).get("tech_stack") or {},
            "data_models": (sprint or {}).get("data_models") or [],
            "repo_layout": (sprint or {}).get("repo_layout"),
            "conventions": (sprint or {}).get("conventions") or {},
        },
        "current_task": in_progress[0] if in_progress else None,
        "next_unblocked_tasks": next_unblocked[:5],
        "task_counts": {
            "todo": len([t for t in tasks if t["status"] == "todo"]),
            "in_progress": len(in_progress),
            "done": len([t for t in tasks if t["status"] == "done"]),
        },
        "recent_decisions": [d for d in decisions if d.get("tag") != "guardrail"][:10],
        "guardrails": [
            {"title": g["title"], "detail": g["detail"], "why": g["why"]} for g in guardrails
        ],
        "secrets_required": secrets_required,
        "secrets_setup_by_name": secrets_setup_by_name,
        "prd_summary": (prd or {}).get("body_md", "")[:2000],
    }


@server.tool()
async def get_prd() -> dict:
    """The full active PRD body (markdown) — what to build and why."""
    prd = art_svc.get_active_prd(_project())
    if not prd:
        return _err("No PRD yet — Maya hasn't published one for this project.")
    return {"version": prd.get("version"), "body_md": prd.get("body_md")}


@server.tool()
async def list_tasks(status: Optional[str] = None) -> Any:
    """List the sprint tasks. Optional status filter: 'todo' | 'in_progress' | 'done'."""
    if status and status not in {"todo", "in_progress", "done"}:
        return _err(f"Invalid status '{status}'. Use one of: todo, in_progress, done.")
    return art_svc.list_tasks(_project(), status=status)


@server.tool()
async def get_task(task_id: str) -> Any:
    """The full spec for one task, by display_id (e.g. 'T-1') or UUID."""
    task = _resolve_task(task_id, _project())
    return task or _err(f"No task with id or display_id '{task_id}'.")


@server.tool()
async def get_guardrails() -> list[dict]:
    """The non-negotiables every change must respect. Read before building."""
    return [
        {"title": d["title"], "detail": d["detail"], "why": d["why"]}
        for d in art_svc.list_decisions(_project())
        if d.get("tag") == "guardrail"
    ]


@server.tool()
async def get_decisions_log() -> list[dict]:
    """The decisions record (newest first), excluding guardrails."""
    return [d for d in art_svc.list_decisions(_project()) if d.get("tag") != "guardrail"]


# ─── Write tools ─────────────────────────────────────────────────────────


@server.tool()
async def update_task_status(task_id: str, status: str, notes: Optional[str] = None) -> Any:
    """Move a task on the board: 'todo' | 'in_progress' | 'done'. Add a short
    note when something is worth the founder knowing."""
    if status not in {"todo", "in_progress", "done"}:
        return _err(f"Invalid status '{status}'. Use one of: todo, in_progress, done.")
    task = _resolve_task(task_id, _project())
    if not task:
        return _err(f"No task '{task_id}'.")
    return art_svc.update_task_status(task["id"], status, notes)


@server.tool()
async def complete_task(task_id: str, summary: str, files_touched: list[str]) -> Any:
    """Mark a task done with a 1-2 sentence summary of what you built and the
    files you touched. The summary shows on the founder's board — plain words."""
    if not summary or len(summary.strip()) < 5:
        return _err("Summary too short — one or two plain sentences on what changed.")
    task = _resolve_task(task_id, _project())
    if not task:
        return _err(f"No task '{task_id}'.")
    return art_svc.complete_task(task["id"], summary, files_touched or [])


@server.tool()
async def log_files_touched(task_id: str, files: list[str]) -> Any:
    """Append files to a task's files_touched list (no status change)."""
    task = _resolve_task(task_id, _project())
    if not task:
        return _err(f"No task '{task_id}'.")
    existing = task.get("files_touched") or []
    merged = list(dict.fromkeys([*existing, *(files or [])]))
    row = (
        require_admin()
        .table("tasks")
        .update({"files_touched": merged})
        .eq("id", task["id"])
        .execute()
    )
    return row.data[0] if row.data else {}


@server.tool()
async def log_decision(
    title: str,
    detail: str,
    why: str,
    decided_by: str = "agent_with_user",
    task_id: Optional[str] = None,
) -> Any:
    """Record a decision made while building (typically with the founder in the
    IDE). decided_by: 'agent_with_user' | 'user' | 'agent_flagged'."""
    if decided_by not in {"agent_with_user", "user", "agent_flagged"}:
        return _err("Invalid decided_by. Use: agent_with_user | user | agent_flagged.")
    pid = _project()
    related = None
    if task_id:
        task = _resolve_task(task_id, pid)
        related = task["id"] if task else None
    return art_svc.log_decision(
        project_id=pid, decided_by=decided_by, title=title,
        detail=detail, why=why, related_task_id=related,
    )


@server.tool()
async def add_task(
    title: str,
    goal: Optional[str] = None,
    description: Optional[str] = None,
    acceptance: Optional[list] = None,
    blocked_by: Optional[list] = None,
    why_needed: Optional[str] = None,
) -> Any:
    """Add a task you discovered mid-build to the CURRENT sprint (e.g. a
    migration or refactor the planned work turns out to need). It appears on
    the founder's board immediately, marked for Maya to sanity-check against
    the MVP scope — so explain `why_needed` in plain words. You cannot create
    a new sprint; when the sprint is done, call request_next_sprint instead."""
    pid = _project()
    if not title or not title.strip():
        return _err("A title is required.")
    sprint = art_svc.get_active_sprint(pid)
    if not sprint:
        return _err("No active sprint — ask the founder to have Maya create one first.")
    sprint_tasks = [t for t in art_svc.list_tasks(pid) if t.get("sprint_id") == sprint["id"]]
    n = len(sprint_tasks) + 1
    task = art_svc.create_task(
        project_id=pid,
        sprint_id=sprint["id"],
        display_id=f"T-{n}",
        title=title.strip(),
        goal=goal,
        description=description,
        acceptance=acceptance if isinstance(acceptance, list) else None,
        blocked_by=blocked_by if isinstance(blocked_by, list) else None,
    )
    # Agent-added work is flagged so Maya reviews scope alignment — the board
    # shows it instantly (the builder isn't blocked), but one planner stays
    # in charge of scope.
    why = "Added by your coding agent"
    if why_needed:
        why += f" — {why_needed.strip()[:200]}"
    require_admin().table("tasks").update(
        {"needs_review": True, "needs_review_why": why}
    ).eq("id", task["id"]).execute()
    return {
        "task": art_svc.get_task(task["id"]),
        "note": "Added to the current sprint and flagged for Maya's review.",
    }


@server.tool()
async def request_next_sprint(
    summary: str,
    learnings: Optional[str] = None,
    suggestions: Optional[str] = None,
) -> Any:
    """Call this when the sprint's work is DONE. Send a short build report:
    `summary` (what got built), `learnings` (what turned out different than
    planned), `suggestions` (what you'd do next). Maya re-reads the linked
    repo, plans the next sprint with the founder grounded in your report, and
    publishes it to the board. You don't create sprints yourself."""
    pid = _project()
    if not summary or len(summary.strip()) < 10:
        return _err("Give a real summary — a few sentences on what got built.")
    parts = [f"**What got built:** {summary.strip()}"]
    if learnings and learnings.strip():
        parts.append(f"**What we learned:** {learnings.strip()}")
    if suggestions and suggestions.strip():
        parts.append(f"**Agent's suggestion for next:** {suggestions.strip()}")
    detail = "\n\n".join(parts)

    decision = art_svc.log_decision(
        project_id=pid,
        decided_by="agent_flagged",
        title="Sprint finished — plan the next one with Maya",
        detail=detail,
        why="The coding agent reports the sprint's work is done; the next sprint needs the founder + Maya.",
        tag="flagged",
        status="open",
        open_type="escalated",
    )

    # Loop closer: re-read the linked repo in the background so Maya plans the
    # next sprint against what was ACTUALLY built, not what she assumed.
    resync = "no repo linked"
    try:
        link_row = (
            require_admin()
            .table("project_repo_links")
            .select("*")
            .eq("project_id", pid)
            .maybe_single()
            .execute()
        )
        link = link_row.data if link_row else None
        if link and link.get("github_connection_id"):
            from app.services import github_client

            asyncio.create_task(
                github_client.ingest_repo(
                    project_id=pid,
                    connection_id=link["github_connection_id"],
                    repo_full_name=link["repo_full_name"],
                    branch=link.get("branch") or "main",
                )
            )
            resync = "repo re-sync started"
    except Exception as e:
        resync = f"repo re-sync skipped ({str(e)[:80]})"

    return {
        "status": "handed_to_maya",
        "open_question_id": decision.get("display_id"),
        "repo": resync,
        "note": (
            "Your report is on the founder's Decisions tab. Maya will plan the "
            "next sprint with them; check back for new tasks."
        ),
    }


@server.tool()
async def request_clarification(task_id: str, question: str) -> Any:
    """Ask Maya to clarify a task. You either get an answer to apply now, or
    it's queued for the founder — work on something else meanwhile."""
    if not question or len(question.strip()) < 8:
        return _err("Question too short — give Maya a complete sentence.")
    pid = _project()
    task = _resolve_task(task_id, pid)
    if not task:
        return _err(f"No task '{task_id}'.")
    from app.services.maya_clarify import clarify

    return await clarify(project_id=pid, task_id=task["id"], question=question)


# ─── ASGI app: key auth wrapper ──────────────────────────────────────────

_mcp_asgi = server.streamable_http_app()


def _extract_key(headers: dict[str, str]) -> str:
    """The key may arrive as X-PS-Key or Authorization: Bearer ps_live_…
    (some MCP clients only support the Authorization header)."""
    key = headers.get("x-ps-key", "")
    if key:
        return key.strip()
    auth = headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def app(scope, receive, send):
    """Validate the project key, bind the project, then hand to the MCP app."""
    if scope["type"] == "http":
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        key = _extract_key(headers)
        project_id = keys_svc.verify(key) if key else None
        if not project_id:
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"missing or invalid ProductSense key (X-PS-Key)"}',
            })
            return
        _project_ctx.set(project_id)
    await _mcp_asgi(scope, receive, send)
