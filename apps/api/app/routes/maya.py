"""Maya chat endpoints. SSE stream + REST helpers."""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import (
    messages as msg_store,
    projects as proj_svc,
    agent_runs_store,
    artifacts as art_svc,
    discovery_artifacts as da_svc,
)
from app.services.auth import CurrentUser, current_user_id
# Phase 5 cutover: the chat is driven by the new Deep Agents coordinator
# (app/deepagent), not the legacy 12-stage MayaSession. DeepMayaSession mirrors
# the legacy external surface (start/send/next_event/abort/is_done/
# is_processing) so the routes below are unchanged.
from app.deepagent.session import DeepMayaSession as MayaSession

router = APIRouter()

# In-memory registry. Survives within one uvicorn worker; the DB is canonical.
_sessions: dict[str, MayaSession] = {}


def _get_or_create_session(project_id: str) -> MayaSession:
    """Return an active session for this project, creating one if missing.

    Why auto-create: after a backend restart (or hot-reload that wiped the
    in-memory `_sessions` dict), the LangGraph checkpointer (Phase 3) STILL
    has the project's graph state on disk under `thread_id=project_id`.
    The frontend's still-open SSE connection points at a dead worker; when
    it reconnects via /maya/message or /maya/stream, we previously 404'd
    here, leaving the chat stuck in 'thinking…' until a manual page refresh.

    With auto-create:
      1. /maya/message arrives → no in-memory session → we build one fresh
         pointing at the same project_id. The graph picks up from the last
         checkpoint, no state lost.
      2. /maya/stream re-opens → same auto-create. SSE driver wraps the
         fresh session's event queue.
      3. Founder hits Stop after restart → /maya/abort sees no in-flight
         turn (because the new session was just created) and returns
         'idle' — also fine, the UI un-stucks itself.

    Replaces _require_session (which 404'd). The only path that still 404s
    is the project itself being missing (auth check happens before this).
    """
    s = _sessions.get(project_id)
    if s and not s.is_done:
        return s
    # Recreate. Don't send the greeting — if there's history this is a
    # resume; if there's no history, the original /maya/start has already
    # delivered the greeting.
    has_history = bool(msg_store.list_recent(project_id, limit=1))
    new_session = MayaSession(project_id)
    _sessions[project_id] = new_session
    new_session.start(send_greeting=not has_history)
    return new_session


# Backwards-compat alias for any external callers; new code uses _get_or_create_session
_require_session = _get_or_create_session


class StartIn(BaseModel):
    project_id: str


class MessageIn(BaseModel):
    project_id: str
    content: str


@router.post("/start")
async def start(payload: StartIn, user_id: CurrentUser) -> dict:
    project = proj_svc.get(user_id, payload.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    existing = _sessions.get(payload.project_id)
    if existing and not existing.is_done:
        # Returning the backend's real processing state so the frontend
        # can mirror it instead of guessing from chat history. After a
        # backend restart the last user message in the DB is orphaned
        # (no in-flight turn), so this is the canonical signal.
        return {
            "status": "already_running",
            "is_resume": True,
            "is_processing": existing.is_processing,
        }

    has_history = bool(msg_store.list_recent(payload.project_id, limit=1))
    session = MayaSession(payload.project_id)
    _sessions[payload.project_id] = session
    session.start(send_greeting=not has_history)
    # Brand-new session — by construction no turn is running yet.
    return {
        "status": "started",
        "is_resume": has_history,
        "is_processing": False,
    }


@router.post("/message")
async def message(payload: MessageIn, user_id: CurrentUser) -> dict:
    if not proj_svc.get(user_id, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Auto-create on missing — the checkpointer holds the durable graph
    # state; we just need an SSE driver wrapper. See _get_or_create_session
    # for why this matters post-restart.
    session = _get_or_create_session(payload.project_id)
    try:
        await session.send(payload.content)
    except asyncio.QueueFull:
        raise HTTPException(status_code=429, detail="Too many messages queued")
    return {"status": "queued"}


class AbortIn(BaseModel):
    project_id: str


@router.post("/abort")
async def abort(payload: AbortIn, user_id: CurrentUser) -> dict:
    """Cancel the in-flight Maya turn for this project. Idempotent — if
    nothing's running, returns {status: 'idle'}.

    Founder-facing: this is what the Stop button calls. Backend cancels
    the asyncio.Task wrapping the current turn so Gemini's ainvoke and
    any child sub-agent dispatches receive CancelledError and unwind.
    The session loop then resumes, ready for the next message.
    """
    if not proj_svc.get(user_id, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    session = _sessions.get(payload.project_id)
    if not session or session.is_done:
        return {"status": "idle"}
    aborted = session.abort()
    return {"status": "aborted" if aborted else "idle"}


@router.get("/stream")
async def stream(
    project_id: str,
    request: Request,
    token: Optional[str] = None,
):
    """SSE stream. EventSource cannot set headers, so we accept ?token=<jwt>."""
    if not token:
        # Authorization header path (covers fetch-based callers)
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    user_id = await current_user_id(authorization=f"Bearer {token}")
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    # Auto-create on missing — common path post-restart when the browser's
    # EventSource reconnects to a fresh worker that has no session yet.
    session = _get_or_create_session(project_id)

    async def gen():
        while True:
            event = await session.next_event()
            if event is None:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/messages")
async def get_messages(project_id: str, user_id: CurrentUser) -> dict:
    """Hydrate the chat surface on app load / project switch.

    Returns four streams the frontend interleaves by timestamp into the
    chronological chat item stream. Each becomes a chat-stream item:

    - messages       — assistant + user text (chat bubbles)
    - agent_runs     — sub-agent dispatches (expandable cards)
    - decisions      — decision-logged chips (per row's created_at)
    - artifact_events — pin/create chips (per discovery_artifact's created_at)

    The latter two are the chip-persistence layer — without them, every
    state-update chip vanishes on reload even though the underlying data
    is intact. Each stream is bounded by its respective store cap; the
    frontend renders them as StateUpdateEntry items.
    """
    if not proj_svc.get(user_id, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    # ── Decision events: every row in `decisions` for the project ──
    decisions: list[dict] = []
    try:
        decisions = art_svc.list_decisions(project_id, include_superseded=True)
    except Exception as e:
        print(f"[/maya/messages] decisions read failed: {e}")

    # ── Artifact events: every live discovery_artifact ────────────────
    artifact_events: list[dict] = []
    try:
        artifact_events = da_svc.list_for_project(project_id)
    except Exception as e:
        print(f"[/maya/messages] artifact_events read failed: {e}")

    return {
        "messages": msg_store.list_all(project_id),
        "agent_runs": agent_runs_store.list_for_project(project_id),
        "decisions": decisions,
        "artifact_events": artifact_events,
    }
