"""Asset service — founder-contributed context layer.

Owns the lifecycle of `project_assets` rows:
  - create()           — register a new asset (status='pending')
  - ingest_async()     — background dispatch to the right ingestor
  - list_for_project() — for the Settings UI / chat asset chips
  - get(), delete()    — singleton + soft-delete
  - load_digests()     — called by Maya's context-layer loader per turn

The ingestion dispatcher routes by mime / extension to one of:
  TextIngestor | PdfIngestor | CodeIngestor | CsvIngestor | ImageIngestor
Repos are ingested by app.services.github_client.ingest_repo (different
input contract — fetched via GitHub API rather than uploaded bytes).
"""
from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Optional

from app.db import require_admin
from app.services.ingestors import (
    Ingestor,
    IngestResult,
    CodeIngestor,
    CsvIngestor,
    ImageIngestor,
    PdfIngestor,
    TextIngestor,
    approx_token_count,
)


# Total token budget for the project context layer fed into Maya's prompt
# each turn. PRD + decisions + assets share this; per-asset cap is 3000
# (in ingestors/base.py). Newest-first ordering applies.
MAYA_CONTEXT_TOKEN_BUDGET = 8000


# ─── Dispatcher ───────────────────────────────────────────────────────────


def _pick_ingestor(mime: Optional[str], display_name: str) -> Ingestor:
    """Route to the most specific ingestor that claims this file.

    Order matters: CSV before Text (.csv is text/csv), Image before
    anything else. Falls back to TextIngestor (which decodes utf-8/latin-1
    and stores the body as-is).
    """
    candidates: list[type[Ingestor]] = [
        ImageIngestor,
        PdfIngestor,
        CsvIngestor,
        CodeIngestor,
        TextIngestor,
    ]
    for cls in candidates:
        if cls.handles(mime, display_name):   # type: ignore[attr-defined]
            return cls()
    return TextIngestor()


# ─── CRUD ─────────────────────────────────────────────────────────────────


def create(
    *,
    project_id: str,
    asset_type: str,                 # 'file' | 'repo' | 'url'
    source_kind: str,                # 'upload' | 'github_repo' | 'web_url'
    display_name: str,
    source_ref: Optional[str] = None,
    mime_type: Optional[str] = None,
    size_bytes: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Insert a new asset row in 'pending' state. Caller is expected to
    kick off ingestion via ingest_async()."""
    db = require_admin()
    payload = {
        "project_id": project_id,
        "asset_type": asset_type,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "display_name": display_name,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "status": "pending",
        "metadata": metadata or {},
    }
    row = db.table("project_assets").insert(payload).execute()
    return (row.data or [{}])[0]


def update(asset_id: str, **patch) -> dict:
    db = require_admin()
    row = (
        db.table("project_assets")
        .update(patch)
        .eq("id", asset_id)
        .execute()
    )
    return (row.data or [{}])[0]


def get(asset_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("project_assets")
        .select("*")
        .eq("id", asset_id)
        .maybe_single()
        .execute()
    )
    return row.data if row else None


def list_for_project(project_id: str) -> list[dict]:
    """Live (non-deleted) assets, newest first."""
    db = require_admin()
    rows = (
        db.table("project_assets")
        .select("*")
        .eq("project_id", project_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data or []


def delete(asset_id: str) -> dict:
    """Soft-delete — sets deleted_at."""
    return update(asset_id, deleted_at=datetime.now(timezone.utc).isoformat())


# ─── Context-layer loader (used by Maya per turn) ─────────────────────────


def load_digests_for_maya(
    project_id: str,
    *,
    budget_tokens: int = MAYA_CONTEXT_TOKEN_BUDGET,
) -> str:
    """Build the project-context system block Maya reads per turn.

    Pulls ready (non-deleted) digests, newest-first, packing as many as fit
    in `budget_tokens`. Returns an empty string when there's nothing to add
    (Maya then runs with just her base prompt).
    """
    rows = (
        require_admin()
        .table("project_assets")
        .select("display_name,asset_type,digest_md,digest_tokens,created_at")
        .eq("project_id", project_id)
        .eq("status", "ready")
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    assets = rows.data or []
    if not assets:
        return ""

    used = 0
    blocks: list[str] = []
    truncated = 0
    for a in assets:
        digest = a.get("digest_md") or ""
        if not digest:
            continue
        cost = a.get("digest_tokens") or approx_token_count(digest)
        if used + cost > budget_tokens:
            truncated += 1
            continue
        used += cost
        type_tag = a.get("asset_type") or "asset"
        blocks.append(f"### {type_tag.title()}: {a.get('display_name', 'asset')}\n\n{digest}")

    if not blocks:
        return ""

    header = (
        "# Project context layer\n\n"
        "The founder has attached the following materials. Treat them as "
        "background reading — like a PRD or a decisions log. Don't recap "
        "them in chat; reference them when relevant.\n"
    )
    if truncated:
        header += f"\n_({truncated} additional asset(s) omitted to fit context budget.)_\n"

    return header + "\n\n---\n\n".join([""] + blocks)


# ─── Ingestion ────────────────────────────────────────────────────────────


async def ingest_file_inline(
    *,
    asset_id: str,
    content: bytes,
    display_name: str,
    mime_type: Optional[str],
) -> None:
    """Run the dispatcher synchronously inside an asyncio task. Caller
    should `asyncio.create_task(...)` this from the upload route so the
    HTTP request returns quickly.

    Best-effort: failures land in the row's `error_text` and `status='error'`
    but never raise out of this function.
    """
    update(asset_id, status="processing")
    try:
        ingestor = _pick_ingestor(mime_type, display_name)
        result: IngestResult = await ingestor.ingest(
            content=content, display_name=display_name, mime_type=mime_type,
        )
        update(
            asset_id,
            status="error" if result.error else "ready",
            digest_md=result.digest_md,
            digest_tokens=result.digest_tokens,
            metadata=result.metadata,
            error_text=result.error,
        )
    except Exception as e:
        traceback.print_exc()
        update(
            asset_id,
            status="error",
            error_text=str(e)[:1000],
        )


def schedule_ingest(
    *,
    asset_id: str,
    content: bytes,
    display_name: str,
    mime_type: Optional[str],
) -> None:
    """Fire-and-forget ingestion. The endpoint that uploads a file calls
    this so the HTTP response is fast and the digest fills in asynchronously."""
    asyncio.create_task(
        ingest_file_inline(
            asset_id=asset_id,
            content=content,
            display_name=display_name,
            mime_type=mime_type,
        )
    )
