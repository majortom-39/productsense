"""ProductSense API entry point.

Run dev:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# ─── Windows event-loop policy fix (BEFORE any other imports that touch asyncio) ─
# psycopg's async driver — used by the LangGraph PostgresSaver — requires
# the SelectorEventLoop. Windows defaults to ProactorEventLoop, which fails
# with "Psycopg cannot use the 'ProactorEventLoop' to run in async mode".
# Setting the policy here, before uvicorn (or anything else) creates its
# event loop, makes the whole app use SelectorEventLoop on Windows. No-op
# on Linux/macOS (default loop there already works with psycopg).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.routes import health, projects, maya, artifacts, mcp_proxy, assets, integrations
from app.services import checkpointer as _checkpointer_svc
from app import mcp_remote


# Boot banner — makes it obvious in logs which process/code is running.
_STARTED_AT = datetime.now(timezone.utc).isoformat()
print(f"[ProductSense API] Loaded at {_STARTED_AT}")


async def _prewarm_vertex() -> None:
    """Fire a tiny Vertex call so the gRPC channel, OAuth token, and
    LangSmith tracer are all ready BEFORE the first founder message lands.

    Without this, the very first user-facing Maya turn pays for:
      - Vertex gRPC channel init (~3-5s)
      - GCP credentials fetch (~2-3s on cold-cache machines)
      - LangSmith tracer client init (~1-2s)
    All of which are one-time per process. Pre-warming during lifespan
    means the founder's first message goes straight to a hot path.

    Best-effort: any error is swallowed (the app still works without
    pre-warm; first turn just pays the cost). Bounded by a 30s timeout."""
    try:
        from app.deepagent.models import build_maya_model
        llm = build_maya_model()
        # Smallest possible probe — single-word reply, no tools, no thinking
        # budget needed. The OUTPUT is irrelevant; we just need to traverse
        # every initialization path.
        await asyncio.wait_for(llm.ainvoke("warm"), timeout=30.0)
        print("[main] Vertex pre-warm complete")
    except asyncio.TimeoutError:
        print("[main] Vertex pre-warm timed out (>30s) — first turn may still be cold")
    except Exception as e:
        print(f"[main] Vertex pre-warm skipped: {str(e)[:120]}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the LangGraph checkpointer connection pool on startup, close
    on shutdown. Graceful: degrades to stateless mode if SUPABASE_DB_URL
    is unset or the DB is unreachable — never blocks app boot.

    Also fires a Vertex pre-warm (best-effort, non-blocking) so the first
    user message doesn't pay cold-start costs."""
    await _checkpointer_svc.init_checkpointer()
    # Schedule pre-warm as a background task so it doesn't block app boot.
    # If a user message arrives in the first ~5-10s after start, they'll
    # still pay some cold-start; but the more common case (a user opens
    # the page, thinks, types) gets a hot pipeline.
    asyncio.create_task(_prewarm_vertex())
    try:
        # The hosted MCP endpoint's session manager must be running for the
        # mounted /mcp app to serve requests (stateless mode still routes
        # through it).
        async with mcp_remote.server.session_manager.run():
            yield
    finally:
        await _checkpointer_svc.close_checkpointer()


app = FastAPI(
    title="ProductSense API",
    description="Maya orchestrator + sub-agents + REST endpoints",
    version="0.0.1",
    lifespan=lifespan,
)

# Order matters — outermost middleware wraps innermost. Add security headers
# first so they're applied even on rate-limit responses.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)

app.include_router(health.router)
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(maya.router, prefix="/maya", tags=["maya"])
app.include_router(artifacts.router, tags=["artifacts"])
app.include_router(assets.router, tags=["assets"])
app.include_router(integrations.router, tags=["integrations"])
app.include_router(mcp_proxy.router, tags=["mcp"])

# The hosted MCP endpoint the founder's coding agent connects to. Key-authed
# (X-PS-Key / Bearer ps_live_…) inside the mounted app itself — see mcp_remote.
app.mount("/mcp", mcp_remote.app)


class _McpPathNormalizer:
    """Map the exact path '/mcp' to '/mcp/' before routing.

    Starlette's Mount would otherwise 307-redirect the bare path, and not every
    MCP client follows redirects on POST — the connect snippet advertises
    '/mcp', so both spellings must just work."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_McpPathNormalizer)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "ProductSense API",
        "version": "0.0.1",
        "status": "scaffolding",
    }
