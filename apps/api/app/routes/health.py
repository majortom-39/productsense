from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.db import supabase_admin

router = APIRouter()

# Captured at module import time → same instant the process started.
# Surfaced via /health so we can tell whether the running uvicorn is on
# current code or stale (e.g. when --reload didn't unload an old module
# that's since been deleted from disk).
_PROCESS_STARTED_AT = datetime.now(timezone.utc).isoformat()


@router.get("/health")
async def health() -> dict[str, object]:
    """Lightweight liveness + dependency check.

    `process_started_at` is set at API process startup. Compare against
    when YOU started uvicorn — if it doesn't match (e.g. it's an hour
    older), you're talking to a stale process. Restart uvicorn.

    `code_revision` lists which feature surfaces exist in this build.
    If any of these are missing on the running process but exist in your
    repo, the process is stale.
    """
    # Probe whether key Phase 11 modules are importable. A stale process
    # might still respond to /health without these.
    has_asset_routes = True
    try:
        import app.routes.assets  # noqa: F401
    except ImportError:
        has_asset_routes = False
    has_integrations = True
    try:
        import app.routes.integrations  # noqa: F401
    except ImportError:
        has_integrations = False
    has_discovery_artifacts = True
    try:
        import app.services.discovery_artifacts  # noqa: F401
    except ImportError:
        has_discovery_artifacts = False

    return {
        "status": "ok",
        "process_started_at": _PROCESS_STARTED_AT,
        "supabase_configured": supabase_admin is not None,
        "vertex_project_configured": bool(settings.gcp_project_id),
        "firecrawl_configured": bool(settings.firecrawl_api_key),
        "code_revision": {
            "asset_routes": has_asset_routes,
            "integrations_routes": has_integrations,
            "discovery_artifacts_service": has_discovery_artifacts,
        },
    }
