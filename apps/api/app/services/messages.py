"""Conversation messages persistence (one row per turn).

`save()` does a single synchronous insert. `list_recent()` / `list_all()` read
the project's chat history for hydration. The durable conversation state Maya
reasons over lives in the LangGraph checkpoint; this table is the chat surface's
replay log.

(Historical note: this module used to fire-and-forget a per-message embedding
for a `search_old_chat` semantic-search tool. That retrieval layer is gone — the
Deep Agents coordinator keeps linear checkpointed history and never searched
those embeddings — so the embedding write was removed.)
"""
from __future__ import annotations

from typing import Optional

from app.db import require_admin


def save(
    project_id: str,
    role: str,                       # 'user' | 'assistant' | 'system'
    content: str,
    agent: Optional[str] = None,     # e.g. 'maya'
    tool_call: Optional[dict] = None,
    quoted: Optional[str] = None,
) -> dict:
    db = require_admin()
    payload: dict = {
        "project_id": project_id,
        "role": role,
        "content": content,
    }
    if agent:
        payload["agent"] = agent
    if tool_call:
        payload["tool_call"] = tool_call
    if quoted:
        payload["quoted"] = quoted
    row = db.table("messages").insert(payload).execute()
    return row.data[0] if row.data else {}


def list_recent(project_id: str, limit: int = 15) -> list[dict]:
    """Newest-first slice, then reversed to chronological order."""
    db = require_admin()
    rows = (
        db.table("messages")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(rows.data or []))


def list_all(project_id: str) -> list[dict]:
    db = require_admin()
    rows = (
        db.table("messages")
        .select("*")
        .eq("project_id", project_id)
        .order("created_at")
        .execute()
    )
    return rows.data or []
