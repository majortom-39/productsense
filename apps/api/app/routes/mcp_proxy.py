"""Endpoints used by the MCP server to act on a project.

These are mounted under the same JWT auth as the rest of the api. The MCP
server passes through the user's bearer token, so RLS-equivalent checks
still apply (project ownership verified per call).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import artifacts as art_svc, projects as proj_svc
from app.services.auth import CurrentUser
from app.services.maya_clarify import clarify

router = APIRouter()


def _ensure_owns(user_id: str, project_id: str) -> None:
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


# ─── Task completion / files ──────────────────────────────────────────────

class CompleteIn(BaseModel):
    summary: str
    files_touched: list[str]


@router.post("/projects/{project_id}/tasks/{task_id}/complete")
async def complete_task(
    project_id: str, task_id: str, payload: CompleteIn, user_id: CurrentUser
) -> dict:
    _ensure_owns(user_id, project_id)
    task = art_svc.get_task(task_id)
    if not task or task.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": art_svc.complete_task(task_id, payload.summary, payload.files_touched)}


class FilesIn(BaseModel):
    files: list[str]


@router.post("/projects/{project_id}/tasks/{task_id}/files")
async def log_files(
    project_id: str, task_id: str, payload: FilesIn, user_id: CurrentUser
) -> dict:
    _ensure_owns(user_id, project_id)
    task = art_svc.get_task(task_id)
    if not task or task.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    existing = task.get("files_touched") or []
    merged = list(dict.fromkeys([*existing, *payload.files]))  # dedupe, preserve order
    from app.db import require_admin
    row = require_admin().table("tasks").update({"files_touched": merged}).eq("id", task_id).execute()
    return {"task": row.data[0] if row.data else {}}


# ─── Decisions create ────────────────────────────────────────────────────

class DecisionIn(BaseModel):
    decided_by: str
    title: str
    detail: str
    why: str
    related_task_id: str | None = None
    tag: str | None = None


@router.post("/projects/{project_id}/decisions")
async def create_decision(
    project_id: str, payload: DecisionIn, user_id: CurrentUser
) -> dict:
    _ensure_owns(user_id, project_id)
    return {"decision": art_svc.log_decision(
        project_id=project_id,
        decided_by=payload.decided_by,
        title=payload.title,
        detail=payload.detail,
        why=payload.why,
        related_task_id=payload.related_task_id,
        tag=payload.tag,
    )}


# ─── Clarification (Tier 1 / Tier 3) ─────────────────────────────────────

class ClarifyIn(BaseModel):
    task_id: str
    question: str


@router.post("/projects/{project_id}/maya/clarify")
async def maya_clarify(
    project_id: str, payload: ClarifyIn, user_id: CurrentUser
) -> dict:
    _ensure_owns(user_id, project_id)
    return await clarify(
        project_id=project_id,
        task_id=payload.task_id,
        question=payload.question,
    )
