"""Read endpoints for PRD, sprint, decisions, research."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import artifacts as svc, projects as proj_svc
from app.services.auth import CurrentUser

router = APIRouter()


def _ensure_owns(user_id: str, project_id: str) -> None:
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/{project_id}/prd")
async def get_prd(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    prd = svc.get_active_prd(project_id)
    if not prd:
        return {"prd": None}
    return {"prd": prd}


@router.get("/projects/{project_id}/sprints")
async def list_sprints(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    return {"sprints": svc.list_sprints(project_id)}


@router.get("/projects/{project_id}/tasks")
async def list_tasks(project_id: str, user_id: CurrentUser, status: str | None = None) -> dict:
    _ensure_owns(user_id, project_id)
    return {"tasks": svc.list_tasks(project_id, status=status)}


class TaskUpdate(BaseModel):
    status: str
    agent_note: str | None = None


@router.patch("/projects/{project_id}/tasks/{task_id}")
async def update_task(
    project_id: str, task_id: str, payload: TaskUpdate, user_id: CurrentUser
) -> dict:
    _ensure_owns(user_id, project_id)
    task = svc.get_task(task_id)
    if not task or task.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": svc.update_task_status(task_id, payload.status, payload.agent_note)}


@router.get("/projects/{project_id}/decisions")
async def list_decisions(
    project_id: str,
    user_id: CurrentUser,
    status: str | None = None,
    include_superseded: bool = False,
) -> dict:
    """Return decisions for the dashboard.

    By default, superseded decisions are hidden — the dashboard and the
    coding agent (via MCP) see only the canonical, active set. Pass
    `include_superseded=true` to surface the full audit trail (the
    decisions tab has a 'Show superseded' toggle that uses this).
    """
    _ensure_owns(user_id, project_id)
    return {"decisions": svc.list_decisions(
        project_id,
        status=status,
        include_superseded=include_superseded,
    )}


@router.get("/projects/{project_id}/discovery")
async def list_discovery(project_id: str, user_id: CurrentUser) -> dict:
    """List Maya-curated discovery artifacts for the dashboard.

    Under the dynamic-artifacts model, this returns rows from
    `discovery_artifacts` (only Maya-pinned / Maya-synthesized cards +
    stage-locked outputs), NOT raw sub-agent runs. The chat replays raw
    runs from `agent_runs`.

    There is no founder-facing refresh endpoint by design — Maya owns
    artifact lifecycle. If a card is outdated, the founder asks Maya
    in chat and she re-runs the affected sub-agents herself.
    """
    _ensure_owns(user_id, project_id)
    return {"discovery": svc.list_discovery(project_id)}


@router.get("/projects/{project_id}/solutions")
async def list_solutions(project_id: str, user_id: CurrentUser) -> dict:
    """Candidate solutions to the validated problem (deepagent §6).

    Maya diverges into several solutions then converges on a recommendation
    (`recommended=true`). The MVP cut downstream turns the chosen solution(s)
    into features.
    """
    _ensure_owns(user_id, project_id)
    return {"solutions": svc.list_solutions(project_id)}


@router.get("/projects/{project_id}/features")
async def list_features(project_id: str, user_id: CurrentUser) -> dict:
    """Features shaped from the chosen solution(s). `in_mvp` marks the cut."""
    _ensure_owns(user_id, project_id)
    return {"features": svc.list_features(project_id)}


@router.get("/projects/{project_id}/reviews")
async def list_reviews(project_id: str, user_id: CurrentUser) -> dict:
    """Nodes flagged needs_review by the coherence engine (deepagent §8).

    When an upstream node materially changes, its direct dependents are
    flagged for another look. This surfaces the flat list enriched with each
    node's title so the founder/Maya can see what a change rippled into.
    """
    _ensure_owns(user_id, project_id)
    return {"reviews": svc.list_reviews(project_id)}


# Back-compat alias: the frontend will be updated, but other consumers
# (e.g. scripts) may still hit /research. Identical payload, deprecated.
@router.get("/projects/{project_id}/research")
async def list_research_alias(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    return {"research": svc.list_discovery(project_id)}
