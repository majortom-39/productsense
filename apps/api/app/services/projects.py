"""Project CRUD against Supabase. Service-role client bypasses RLS;
we manually scope every query by user_id from the validated JWT.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.db import require_admin


def list_for_user(user_id: str) -> list[dict]:
    db = require_admin()
    rows = (
        db.table("projects")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data or []


def create(user_id: str, name: str, icon: Optional[str], entry_type: str) -> dict:
    db = require_admin()
    row = (
        db.table("projects")
        .insert({
            "user_id": user_id,
            "name": name,
            "icon": icon,
            "entry_type": entry_type,
        })
        .execute()
    )
    return row.data[0]


def get(user_id: str, project_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return row.data if row else None


def delete(user_id: str, project_id: str) -> bool:
    db = require_admin()
    existing = get(user_id, project_id)
    if not existing:
        return False
    db.table("projects").delete().eq("id", project_id).eq("user_id", user_id).execute()
    return True
