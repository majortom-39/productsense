"""Integration routes — GitHub OAuth + repo linking.

Endpoints:
    GET    /integrations/github/start             — returns the GitHub
                                                    authorize URL the
                                                    web app redirects to.
    POST   /integrations/github/exchange          — body: {code} → exchanges
                                                    via GitHub's token API,
                                                    persists connection.
    GET    /integrations/github/connections       — list this user's connections.
    DELETE /integrations/github/connections/{id}  — disconnect.
    GET    /integrations/github/repos?conn_id=... — list this connection's repos.

    POST   /projects/{pid}/repo                   — body: {connection_id,
                                                    repo_full_name, branch}
                                                    → links repo + kicks off
                                                    ingest digest job.
    GET    /projects/{pid}/repo                   — current link (or null).
    DELETE /projects/{pid}/repo                   — unlink (asset stays as
                                                    a regular asset row).
"""
from __future__ import annotations

import asyncio
from secrets import token_urlsafe
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db import require_admin
from app.services import github_client, projects as proj_svc
from app.services.auth import CurrentUser


router = APIRouter()


# ─── GitHub OAuth flow ────────────────────────────────────────────────────


@router.get("/integrations/github/start")
async def github_start(user_id: CurrentUser) -> dict:
    """Return the authorize URL the web app should redirect to. We also
    return a short-lived state token the web app should round-trip back
    so CSRF stays clean."""
    if not settings.github_oauth_client_id:
        raise HTTPException(
            status_code=503,
            detail="GitHub integration not configured. Set GITHUB_OAUTH_CLIENT_ID/SECRET.",
        )
    state = token_urlsafe(24)
    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": "repo read:user",
        "state": state,
    }
    return {
        "authorize_url": f"https://github.com/login/oauth/authorize?{urlencode(params)}",
        "state": state,
    }


class ExchangeBody(BaseModel):
    code: str


@router.post("/integrations/github/exchange")
async def github_exchange(payload: ExchangeBody, user_id: CurrentUser) -> dict:
    if not settings.github_oauth_client_id:
        raise HTTPException(status_code=503, detail="GitHub integration not configured.")
    try:
        connection = await github_client.save_connection(user_id=user_id, code=payload.code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)[:300])
    return {"connection": connection}


@router.get("/integrations/github/connections")
async def list_github_connections(user_id: CurrentUser) -> dict:
    return {"connections": github_client.list_connections_for_user(user_id)}


@router.delete("/integrations/github/connections/{connection_id}")
async def delete_github_connection(connection_id: str, user_id: CurrentUser) -> dict:
    conn = github_client.get_connection(connection_id)
    if not conn or conn.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    github_client.delete_connection(connection_id)
    return {"status": "deleted"}


@router.get("/integrations/github/repos")
async def list_github_repos(conn_id: str, user_id: CurrentUser) -> dict:
    conn = github_client.get_connection(conn_id)
    if not conn or conn.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        repos = await github_client.list_repos(conn_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API failed: {str(e)[:200]}")
    return {"repos": repos}


# ─── Project ↔ repo linking ───────────────────────────────────────────────


def _ensure_owns(user_id: str, project_id: str) -> None:
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


class LinkRepoBody(BaseModel):
    connection_id: str
    repo_full_name: str
    branch: str = "main"


@router.post("/projects/{project_id}/repo")
async def link_repo(project_id: str, payload: LinkRepoBody, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    conn = github_client.get_connection(payload.connection_id)
    if not conn or conn.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Fire-and-forget ingestion — the asset row is created/updated
    # synchronously so the response includes the row id for polling.
    asyncio.create_task(
        github_client.ingest_repo(
            project_id=project_id,
            connection_id=payload.connection_id,
            repo_full_name=payload.repo_full_name,
            branch=payload.branch,
        )
    )
    return {"status": "linking", "repo_full_name": payload.repo_full_name}


@router.get("/projects/{project_id}/repo")
async def get_repo_link(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    db = require_admin()
    row = (
        db.table("project_repo_links")
        .select("*")
        .eq("project_id", project_id)
        .maybe_single()
        .execute()
    )
    return {"link": row.data if row else None}


@router.delete("/projects/{project_id}/repo")
async def unlink_repo(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    db = require_admin()
    db.table("project_repo_links").delete().eq("project_id", project_id).execute()
    return {"status": "unlinked"}
