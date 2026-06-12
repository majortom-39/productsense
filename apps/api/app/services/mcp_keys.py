"""MCP key service — the `ps_live_…` credential a founder's coding agent uses.

One ACTIVE key per project: generating a new one revokes the old (rotation).
Only the sha256 hash is stored; the plaintext is returned exactly once at
generation time for the connect snippet. Every authed MCP request stamps
`last_seen_at`, which powers the "agent connected" indicator in the UI.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from app.db import require_admin

KEY_PREFIX = "ps_live_"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate(project_id: str, label: str | None = None) -> dict:
    """Mint a fresh key for the project, revoking any previous active key.

    Returns {key, key_prefix, created_at} — `key` is the ONLY time the
    plaintext leaves this module; it is never stored or retrievable again.
    """
    db = require_admin()
    key = KEY_PREFIX + secrets.token_hex(20)
    prefix = key[: len(KEY_PREFIX) + 6] + "…"
    (
        db.table("mcp_keys")
        .update({"revoked_at": _now()})
        .eq("project_id", project_id)
        .is_("revoked_at", "null")
        .execute()
    )
    row = (
        db.table("mcp_keys")
        .insert({
            "project_id": project_id,
            "key_hash": _hash(key),
            "key_prefix": prefix,
            "label": label,
        })
        .execute()
    )
    created = (row.data or [{}])[0]
    return {"key": key, "key_prefix": prefix, "created_at": created.get("created_at")}


def verify(key: str) -> Optional[str]:
    """Return the project_id for a live key, else None. Stamps last_seen_at."""
    if not key or not key.startswith(KEY_PREFIX):
        return None
    db = require_admin()
    row = (
        db.table("mcp_keys")
        .select("id,project_id,revoked_at")
        .eq("key_hash", _hash(key))
        .maybe_single()
        .execute()
    )
    data = row.data if row else None
    if not data or data.get("revoked_at"):
        return None
    try:
        db.table("mcp_keys").update({"last_seen_at": _now()}).eq("id", data["id"]).execute()
    except Exception:
        pass  # the stamp is best-effort; never block the agent on it
    return data["project_id"]


def status(project_id: str) -> dict:
    """Connection status for the UI: does an active key exist, when was the
    agent last seen. Never returns key material."""
    db = require_admin()
    rows = (
        db.table("mcp_keys")
        .select("key_prefix,created_at,last_seen_at")
        .eq("project_id", project_id)
        .is_("revoked_at", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    active = (rows.data or [None])[0]
    if not active:
        return {"active": False, "key_prefix": None, "created_at": None, "last_seen_at": None}
    return {
        "active": True,
        "key_prefix": active["key_prefix"],
        "created_at": active["created_at"],
        "last_seen_at": active["last_seen_at"],
    }


def revoke(project_id: str) -> None:
    """Revoke all active keys for the project (disconnect the agent)."""
    db = require_admin()
    (
        db.table("mcp_keys")
        .update({"revoked_at": _now()})
        .eq("project_id", project_id)
        .is_("revoked_at", "null")
        .execute()
    )
