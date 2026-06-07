"""Read + write helpers for the `agent_runs` table.

Reads power the chat hydration + dashboard. Writes (`start_run`/`finish_run`)
are called by `DeepMayaSession` when Maya dispatches a specialist, so the
dispatch cards survive a reload (the live SSE stream is gone after a refresh —
this table is the durable record the hydration replays from).

Naming: `agent_runs_store` (not `agent_runs`) to avoid shadowing the
table name in places where a local also called `agent_runs` would be
ambiguous.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.db import require_admin


def list_for_project(project_id: str, limit: int = 500) -> list[dict]:
    """Chronologically-ordered list of every run on this project.

    Returns the fields the chat hydration needs to reconstruct an
    AgentCallEntry on reload: agent name, query (so the question chip
    can render), status, output_payload (so the result body renders
    via ArtifactRenderer), timestamps, and message_id (so dispatches
    can be grouped under the Maya turn that triggered them).

    The 500-row cap is a soft guard against runaway projects; we can
    paginate if it ever matters.
    """
    db = require_admin()
    rows = (
        db.table("agent_runs")
        .select(
            "id,agent_name,invoked_by,query,status,output_payload,"
            "message_id,started_at,ended_at,duration_ms,error_text"
        )
        .eq("project_id", project_id)
        .order("started_at")
        .limit(limit)
        .execute()
    )
    return rows.data or []


def get(run_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("agent_runs")
        .select("*")
        .eq("id", run_id)
        .maybe_single()
        .execute()
    )
    return row.data if row else None


# ─── Writes ─────────────────────────────────────────────────────────────────
# Best-effort: persistence must never break a Maya turn, so both helpers swallow
# their errors (the dispatch still streamed live; only reload-replay is lost).

def _query_hash(agent_name: str, query: str) -> str:
    return hashlib.sha256(f"{agent_name}::{query}".encode("utf-8")).hexdigest()


def start_run(project_id: str, agent_name: str, query: str) -> Optional[str]:
    """Record a 'running' dispatch when Maya hands a specialist a task.
    Returns the new run id, or None on failure."""
    try:
        db = require_admin()
        row = (
            db.table("agent_runs")
            .insert({
                "project_id": project_id,
                "agent_name": agent_name or "specialist",
                "invoked_by": "maya",
                "query": query or "",
                "query_hash": _query_hash(agent_name or "", query or ""),
            })
            .execute()
        )
        return (row.data or [{}])[0].get("id")
    except Exception as e:
        print(f"[agent_runs_store] start_run failed: {str(e)[:200]}")
        return None


def finish_run(run_id: Optional[str], status: str, output_payload: Optional[dict] = None) -> None:
    """Move a run to its terminal state (`complete` | `clarification_needed` |
    `error`) and store the specialist's structured result."""
    if not run_id:
        return
    try:
        db = require_admin()
        (
            db.table("agent_runs")
            .update({
                "status": status,
                "output_payload": output_payload,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", run_id)
            .execute()
        )
    except Exception as e:
        print(f"[agent_runs_store] finish_run failed: {str(e)[:200]}")
