"""ProductSense MCP server (Streamable HTTP).

Per MCP spec 2025-11-25 + security best practices:
  - Origin header validated on every request (DNS rebinding mitigation)
  - Tools return tool execution errors via {isError: true, content: [...]}
    instead of raising JSON-RPC errors for business-logic failures, so the
    LLM can self-correct
  - Structured logging with request IDs and tool latencies
  - Input validation via Pydantic-equivalent annotations on tool args
  - Localhost binding by default; HTTPS expected in production behind a proxy

Authentication model (v1):
  Per-project tokens passed via env at server-launch time:
    PRODUCTSENSE_API_URL    base URL of api app
    PRODUCTSENSE_PROJECT_ID UUID of the linked project
    PRODUCTSENSE_TOKEN      Supabase JWT (or future per-project key)

  Each MCP server instance is single-tenant (one process per project). For
  multi-tenant hosting, run a process per project or upgrade to OAuth 2.1.

Run:
    uvicorn server:app --host 127.0.0.1 --port 8001
"""
from __future__ import annotations

import functools
import logging
import os
import time
import uuid
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


# ─── Config ──────────────────────────────────────────────────────────────

API_URL = os.getenv("PRODUCTSENSE_API_URL", "http://localhost:8000")
PROJECT_ID = os.getenv("PRODUCTSENSE_PROJECT_ID", "")
TOKEN = os.getenv("PRODUCTSENSE_TOKEN", "")
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.getenv(
        "MCP_ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,null",
    ).split(",")
    if o.strip()
}

logging.basicConfig(
    level=os.getenv("MCP_LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
)
log = logging.getLogger("productsense.mcp")


# ─── Server instance ─────────────────────────────────────────────────────

server = FastMCP("productsense")


# ─── HTTP helpers ────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }


async def _get(path: str) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{API_URL}{path}", headers=_headers())
        r.raise_for_status()
        return r.json()


async def _post(path: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{API_URL}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


async def _patch(path: str, body: dict) -> Any:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.patch(f"{API_URL}{path}", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json()


# Decorator that turns API exceptions into tool-execution errors (not protocol errors)
# so the LLM can read the message and self-correct. Uses functools.wraps so the
# original function's signature is preserved — FastMCP introspects it to derive
# the tool's input schema.
def _tool_safe(fn):
    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        rid = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        log.info(
            f'{{"event":"tool_call_start","rid":"{rid}","tool":"{fn.__name__}",'
            f'"args":{_safe_json(kwargs)}}}'
        )
        try:
            result = await fn(*args, **kwargs)
            ms = int((time.perf_counter() - started) * 1000)
            log.info(
                f'{{"event":"tool_call_done","rid":"{rid}","tool":"{fn.__name__}",'
                f'"latency_ms":{ms}}}'
            )
            return result
        except httpx.HTTPStatusError as e:
            ms = int((time.perf_counter() - started) * 1000)
            log.warning(
                f'{{"event":"tool_call_http_error","rid":"{rid}","tool":"{fn.__name__}",'
                f'"status":{e.response.status_code},"latency_ms":{ms}}}'
            )
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": f"API call failed ({e.response.status_code}): "
                            f"{e.response.text[:200]}",
                }],
            }
        except Exception as e:
            ms = int((time.perf_counter() - started) * 1000)
            log.error(
                f'{{"event":"tool_call_exception","rid":"{rid}","tool":"{fn.__name__}",'
                f'"err":{_safe_json({"message": str(e)[:200]})},"latency_ms":{ms}}}'
            )
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": f"Internal error: {str(e)[:200]}",
                }],
            }
    return wrapped


def _safe_json(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return '"<unserializable>"'


# ─── Read tools ──────────────────────────────────────────────────────────


@server.tool()
@_tool_safe
async def get_session_context() -> dict:
    """Return everything a coding agent needs to resume work in ONE call.

    Includes:
      - macro:    project_brief + north_star (read this first)
      - sprint:   tech_stack, data_models, repo_layout, conventions
      - tasks:    current in-progress + next unblocked + counts
      - decisions: last 10 (excludes guardrails)
      - guardrails: full list of compiled "do not" rules
      - prd:      summary
    """
    [project_resp, tasks_resp, decisions_resp, prd_resp, sprints_resp] = [
        await _get(f"/projects/{PROJECT_ID}"),
        await _get(f"/projects/{PROJECT_ID}/tasks"),
        await _get(f"/projects/{PROJECT_ID}/decisions"),
        await _get(f"/projects/{PROJECT_ID}/prd"),
        await _get(f"/projects/{PROJECT_ID}/sprints"),
    ]
    project = project_resp.get("project", {}) if isinstance(project_resp, dict) else project_resp
    tasks = tasks_resp.get("tasks", [])
    decisions = decisions_resp.get("decisions", [])
    prd = prd_resp.get("prd")
    sprints = sprints_resp.get("sprints", [])

    in_progress = [t for t in tasks if t["status"] == "in_progress"]
    todo = [t for t in tasks if t["status"] == "todo"]
    next_unblocked = [t for t in todo if not t.get("blocked_by")]
    guardrails = [d for d in decisions if d.get("tag") == "guardrail"]
    active_sprint = next((s for s in sprints if s.get("status") == "active"), None) or (sprints[0] if sprints else None)

    # Sprint-wide secrets summary so the coding agent can ask the founder
    # for missing keys upfront in one batch instead of task-by-task.
    # `setup_by_name` carries Kai's per-secret onboarding guidance
    # (signup_url + free_tier_note + ask_phrase) keyed by env var name —
    # the agent reads ask_phrase to request the key from the founder.
    secrets_required: list[str] = []
    secrets_setup_by_name: dict[str, dict] = {}
    for t in tasks:
        if t.get("status") == "done":
            continue
        for s in (t.get("secrets_required") or []):
            if s and s not in secrets_required:
                secrets_required.append(s)
        for entry in (t.get("secrets_setup") or []):
            if isinstance(entry, dict):
                name = entry.get("name")
                if name and name not in secrets_setup_by_name:
                    secrets_setup_by_name[name] = entry

    return {
        "project_id": PROJECT_ID,
        # MACRO — read these first
        "project_brief": project.get("project_brief"),
        "north_star": project.get("north_star"),
        # SPRINT-LEVEL context (one block per sprint, not per task)
        "sprint": {
            "name": active_sprint.get("name") if active_sprint else None,
            "subtitle": active_sprint.get("subtitle") if active_sprint else None,
            "tech_stack": active_sprint.get("tech_stack", {}) if active_sprint else {},
            "data_models": active_sprint.get("data_models", []) if active_sprint else [],
            "repo_layout": active_sprint.get("repo_layout") if active_sprint else None,
            "conventions": active_sprint.get("conventions", {}) if active_sprint else {},
        },
        # WORK
        "current_task": in_progress[0] if in_progress else None,
        "next_unblocked_tasks": next_unblocked[:5],
        "task_counts": {
            "todo": len([t for t in tasks if t["status"] == "todo"]),
            "in_progress": len(in_progress),
            "done": len([t for t in tasks if t["status"] == "done"]),
        },
        # DECISIONS + GUARDRAILS
        "recent_decisions": [d for d in decisions if d.get("tag") != "guardrail"][:10],
        "guardrails": [
            {"title": g["title"], "detail": g["detail"], "why": g["why"]}
            for g in guardrails
        ],
        # SECRETS — what the coding agent needs to onboard from the founder.
        # Workflow: check .env for each name; for any missing one, paste the
        # corresponding ask_phrase into the IDE chat to request the key.
        "secrets_required": secrets_required,
        "secrets_setup_by_name": secrets_setup_by_name,
        # PRD summary (full PRD via get_prd if needed)
        "prd_summary": (prd or {}).get("body_md", "")[:2000],
    }


@server.tool()
@_tool_safe
async def get_prd() -> dict:
    """Return the full active PRD body (markdown)."""
    resp = await _get(f"/projects/{PROJECT_ID}/prd")
    prd = resp.get("prd")
    if not prd:
        return {"isError": True, "content": [{"type": "text", "text": "No PRD yet."}]}
    return {"version": prd.get("version"), "body_md": prd.get("body_md")}


@server.tool()
@_tool_safe
async def list_tasks(status: Optional[str] = None) -> list[dict]:
    """List tasks. Optional status filter: 'todo' | 'in_progress' | 'done'."""
    if status and status not in {"todo", "in_progress", "done"}:
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": f"Invalid status '{status}'. Use one of: todo, in_progress, done.",
            }],
        }
    suffix = f"?status={status}" if status else ""
    resp = await _get(f"/projects/{PROJECT_ID}/tasks{suffix}")
    return resp.get("tasks", [])


@server.tool()
@_tool_safe
async def get_task(task_id: str) -> Optional[dict]:
    """Get the full spec for one task by display_id (e.g. 't1') or UUID."""
    resp = await _get(f"/projects/{PROJECT_ID}/tasks")
    for t in resp.get("tasks", []):
        if t["id"] == task_id or t["display_id"] == task_id:
            return t
    return {
        "isError": True,
        "content": [{
            "type": "text",
            "text": f"No task with id or display_id '{task_id}'.",
        }],
    }


@server.tool()
@_tool_safe
async def get_decisions_log() -> list[dict]:
    """Return the full decisions list (newest first), excluding guardrails."""
    resp = await _get(f"/projects/{PROJECT_ID}/decisions")
    return [d for d in resp.get("decisions", []) if d.get("tag") != "guardrail"]


@server.tool()
@_tool_safe
async def get_guardrails() -> list[dict]:
    """Return guardrails as title/detail/why objects."""
    resp = await _get(f"/projects/{PROJECT_ID}/decisions")
    return [
        {"title": d["title"], "detail": d["detail"], "why": d["why"]}
        for d in resp.get("decisions", [])
        if d.get("tag") == "guardrail"
    ]


# ─── Write tools ─────────────────────────────────────────────────────────


_VALID_TASK_STATUS = {"todo", "in_progress", "done"}


@server.tool()
@_tool_safe
async def update_task_status(task_id: str, status: str, notes: Optional[str] = None) -> dict:
    """Update task status. Valid: todo / in_progress / done."""
    if status not in _VALID_TASK_STATUS:
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": f"Invalid status '{status}'. Use one of: {sorted(_VALID_TASK_STATUS)}.",
            }],
        }
    return await _patch(
        f"/projects/{PROJECT_ID}/tasks/{await _resolve_task_id(task_id)}",
        {"status": status, "agent_note": notes},
    )


@server.tool()
@_tool_safe
async def complete_task(task_id: str, summary: str, files_touched: list[str]) -> dict:
    """Mark a task done with a completion summary and the files touched."""
    if not summary or len(summary.strip()) < 5:
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": "Summary too short — give a 1-2 sentence description of what changed.",
            }],
        }
    real_id = await _resolve_task_id(task_id)
    return await _post(
        f"/projects/{PROJECT_ID}/tasks/{real_id}/complete",
        {"summary": summary, "files_touched": files_touched},
    )


@server.tool()
@_tool_safe
async def log_files_touched(task_id: str, files: list[str]) -> dict:
    """Append files to the task's files_touched list (no status change)."""
    real_id = await _resolve_task_id(task_id)
    return await _post(
        f"/projects/{PROJECT_ID}/tasks/{real_id}/files",
        {"files": files},
    )


_VALID_DECIDED_BY = {
    "agent_with_user", "user", "agent_flagged",
    # maya_autonomous / maya_with_user are reserved for the orchestrator
}


@server.tool()
@_tool_safe
async def log_decision(
    task_id: Optional[str],
    decided_by: str,
    title: str,
    detail: str,
    why: str,
) -> dict:
    """Log a decision the coding agent resolved (typically `agent_with_user`)."""
    if decided_by not in _VALID_DECIDED_BY:
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": f"Invalid decided_by '{decided_by}'. Use one of: {sorted(_VALID_DECIDED_BY)}.",
            }],
        }
    real_id = await _resolve_task_id(task_id) if task_id else None
    return await _post(
        f"/projects/{PROJECT_ID}/decisions",
        {
            "decided_by": decided_by,
            "title": title,
            "detail": detail,
            "why": why,
            "related_task_id": real_id,
        },
    )


# ─── Hot path: clarification routing ─────────────────────────────────────


@server.tool()
@_tool_safe
async def request_clarification(task_id: str, question: str) -> dict:
    """Ask Maya for clarification on a task.

    Returns either:
      - tier=1: an autonomous answer (apply and continue)
      - tier=3: queued response with `next_unblocked_task_ids` (work on something else)
    """
    if not question or len(question.strip()) < 8:
        return {
            "isError": True,
            "content": [{
                "type": "text",
                "text": "Question too short — give Maya a complete sentence to work with.",
            }],
        }
    real_id = await _resolve_task_id(task_id)
    return await _post(
        f"/projects/{PROJECT_ID}/maya/clarify",
        {"task_id": real_id, "question": question},
    )


# ─── Helpers ─────────────────────────────────────────────────────────────


async def _resolve_task_id(maybe_display: str) -> str:
    """Accept either a UUID or a display_id (t1, t2). Return the UUID."""
    if maybe_display and "-" in maybe_display and len(maybe_display) > 20:
        return maybe_display  # already a UUID
    resp = await _get(f"/projects/{PROJECT_ID}/tasks")
    for t in resp.get("tasks", []):
        if t["display_id"] == maybe_display:
            return t["id"]
    return maybe_display  # let the api 404


# ─── ASGI app with Origin validation ─────────────────────────────────────

_inner_app = server.streamable_http_app()


async def app(scope, receive, send):
    """ASGI wrapper: validate Origin (DNS rebinding defence per MCP spec)."""
    if scope["type"] == "http":
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        origin = headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            log.warning(f'{{"event":"origin_blocked","origin":"{origin}"}}')
            await send({
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"origin not allowed"}',
            })
            return
    await _inner_app(scope, receive, send)


def main() -> None:
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("MCP_HOST", "127.0.0.1"),  # localhost-only by default
        port=int(os.getenv("MCP_PORT", "8001")),
    )


if __name__ == "__main__":
    main()
