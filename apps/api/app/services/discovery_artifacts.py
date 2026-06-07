"""Discovery artifacts service — the cards on the Discovery tab.

The Discovery tab reads from `discovery_artifacts`: a flat, chronological feed of
the cards Maya synthesizes (flexible render_kind + structured payload). Maya
reaches these helpers through her domain tools (see app/deepagent/domain_tools.py).

Lifecycle: `create()` adds a card, `delete()` soft-hides it (chat history may
still cite it). Kept separate from artifacts.py because these have a different
shape (render_kind + payload) and a curated, soft-deletable lifecycle.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.db import require_admin


# The render kinds this service accepts — the generic visual shapes the frontend
# ArtifactRenderer can draw. Mirror of domain_tools.MAYA_RENDER_KINDS; server-side
# validation is the last line of defence (an unknown kind coerces to 'text').
VALID_RENDER_KINDS = {
    "text", "table", "matrix", "bar_chart", "line_chart",
    "graph", "persona_cards", "stack_diagram", "mermaid",
    "wireframe_flow",   # Maya's UX screen flows (greyscale mockups)
}


# ─── Reads ────────────────────────────────────────────────────────────────

def list_for_project(project_id: str) -> list[dict]:
    """Live (non-deleted) artifacts for the dashboard, newest first."""
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


def get(artifact_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("discovery_artifacts")
        .select("*")
        .eq("id", artifact_id)
        .maybe_single()
        .execute()
    )
    return row.data if row else None


# ─── Writes ───────────────────────────────────────────────────────────────

def _coerce_render_kind(rk: Optional[str]) -> str:
    return rk if rk in VALID_RENDER_KINDS else "text"


def create(
    *,
    project_id: str,
    title: str,
    render_kind: str,
    payload: dict,
    summary: Optional[str] = None,
) -> dict:
    """Create a discovery card. `render_kind` is coerced to a known shape;
    `payload` carries the structured data for that shape."""
    if not title or not title.strip():
        raise ValueError("title is required")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    db = require_admin()
    row = db.table("discovery_artifacts").insert({
        "project_id": project_id,
        "title": title.strip(),
        "summary": summary,
        "render_kind": _coerce_render_kind(render_kind),
        "payload": payload,
        "created_by": "maya_synthesized",
    }).execute()
    return (row.data or [{}])[0]


def delete(*, artifact_id: str, project_id: str) -> dict:
    """Soft delete — set deleted_at. Idempotent on already-deleted rows."""
    existing = get(artifact_id)
    if not existing:
        raise ValueError(f"artifact not found: {artifact_id}")
    if existing.get("project_id") != project_id:
        raise ValueError("artifact belongs to a different project")
    if existing.get("deleted_at"):
        return existing

    db = require_admin()
    row = (
        db.table("discovery_artifacts")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", artifact_id)
        .execute()
    )
    return (row.data or [{}])[0]
