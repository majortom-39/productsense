"""Asset routes — founder attaches files to a project; the asset manager
ingests them in the background and makes the digest available to Maya as
part of her project context layer.

Endpoints:
    POST   /projects/{pid}/assets                  — multipart upload
    GET    /projects/{pid}/assets                  — list (status + digest)
    GET    /projects/{pid}/assets/{aid}            — get one
    DELETE /projects/{pid}/assets/{aid}            — soft-delete

Ingestion is fire-and-forget: the POST returns immediately with status='pending'.
The frontend polls the list endpoint (or refetches on chat events) until
status flips to 'ready' or 'error'.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from app.services import assets as asset_svc
from app.services import projects as proj_svc
from app.services.auth import CurrentUser


router = APIRouter()

# Cap any single upload at 10 MB. Anything bigger almost certainly isn't
# useful context for Maya (and the ingestor would either truncate hard or
# choke on memory). We reject early with a clean 413 so the frontend can
# show a friendly error rather than receiving a generic upload-failed.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _ensure_owns(user_id: str, project_id: str) -> None:
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/{project_id}/assets")
async def list_assets(project_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    return {"assets": asset_svc.list_for_project(project_id)}


@router.get("/projects/{project_id}/assets/{asset_id}")
async def get_asset(project_id: str, asset_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    asset = asset_svc.get(asset_id)
    if not asset or asset.get("project_id") != project_id or asset.get("deleted_at"):
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"asset": asset}


@router.post("/projects/{project_id}/assets")
async def upload_asset(
    project_id: str,
    user_id: CurrentUser,
    request: Request,
    file: UploadFile = File(...),
    content_length: int | None = Header(default=None),
) -> dict:
    """Upload a single file. Returns immediately with status='pending'.

    The ingestor runs in a background task; the row transitions to
    'processing' then 'ready' (or 'error'). The frontend polls the list
    endpoint to watch the status change.

    Size enforcement is two-stage:
      1. Header pre-check on Content-Length so we reject before reading the
         body — saves the founder a 30s upload of a 50MB video before
         showing them the error.
      2. Post-read check on actual length, in case the client lied in the
         header. Belt-and-braces.
    Both return 413 so the frontend has a single error class to handle.
    """
    _ensure_owns(user_id, project_id)

    # Stage 1: Content-Length header pre-check. The multipart overhead is
    # ~200 bytes (boundary + part headers), trivial vs the 10MB cap. Anything
    # WAY over the cap gets rejected without reading a byte of body. If the
    # header is missing (rare; chunked transfer) we fall through to stage 2.
    if content_length is not None and content_length > MAX_UPLOAD_BYTES + 4096:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({content_length // (1024 * 1024)} MB); "
                f"max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            ),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({len(content) // (1024 * 1024)} MB); "
                f"max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            ),
        )

    display_name = (file.filename or "untitled").strip() or "untitled"
    row = asset_svc.create(
        project_id=project_id,
        asset_type="file",
        source_kind="upload",
        display_name=display_name,
        mime_type=file.content_type,
        size_bytes=len(content),
    )
    asset_svc.schedule_ingest(
        asset_id=row["id"],
        content=content,
        display_name=display_name,
        mime_type=file.content_type,
    )
    return {"asset": row}


@router.delete("/projects/{project_id}/assets/{asset_id}")
async def delete_asset(project_id: str, asset_id: str, user_id: CurrentUser) -> dict:
    _ensure_owns(user_id, project_id)
    asset = asset_svc.get(asset_id)
    if not asset or asset.get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"asset": asset_svc.delete(asset_id)}
