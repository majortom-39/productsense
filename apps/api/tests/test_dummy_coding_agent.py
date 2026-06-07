"""End-to-end "coding agent" test: simulates what a real Cursor/Claude Code
session would do via MCP. Spawns the api, sets up project state, then calls
each MCP tool function directly (bypassing the streaming protocol — that
layer is verified by `test_mcp_origin_validation`).

The test asserts the full workflow round-trips into Supabase:
  1. Coding agent reads context (sees the unblocked task)
  2. Marks task in_progress
  3. Logs an agent_with_user decision
  4. Asks Maya for clarification → Maya responds via Tier 1 or Tier 3
  5. Completes the task with summary + files
  6. Final state in DB shows status=done + decision logged

Skips when real Supabase + Vertex creds aren't loaded.
"""
from __future__ import annotations

import contextlib
import importlib
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

from app.config import settings


pytestmark = pytest.mark.skipif(
    not settings.supabase_service_role_key
    or settings.supabase_service_role_key.startswith("test-")
    or not settings.gcp_project_id
    or settings.gcp_project_id.startswith("test-"),
    reason="Real Supabase + Vertex required",
)


_REPO = Path(__file__).resolve().parents[3]
_API_DIR = _REPO / "apps" / "api"
_MCP_DIR = _REPO / "apps" / "mcp"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _spawn(cmd, env=None, cwd=None, ready_url=None, timeout=30):
    p = subprocess.Popen(
        cmd, env=env, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        if ready_url:
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    if httpx.get(ready_url, timeout=2).status_code < 500:
                        break
                except Exception:
                    pass
                if p.poll() is not None:
                    raise RuntimeError(f"subprocess died (exit {p.returncode})")
                time.sleep(0.5)
            else:
                raise RuntimeError(f"subprocess did not start in {timeout}s")
        yield p
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture(scope="module")
def setup():
    sb = settings.supabase_url
    skey = settings.supabase_service_role_key
    akey = settings.supabase_anon_key
    email = f"mcp-{uuid.uuid4().hex[:8]}@productsense.test"

    user = httpx.post(
        f"{sb}/auth/v1/admin/users",
        json={"email": email, "password": "TestPass123!", "email_confirm": True},
        headers={"apikey": skey, "Authorization": f"Bearer {skey}", "Content-Type": "application/json"},
        timeout=15,
    ).json()
    user_id = user["id"]
    token = httpx.post(
        f"{sb}/auth/v1/token?grant_type=password",
        json={"email": email, "password": "TestPass123!"},
        headers={"apikey": akey, "Content-Type": "application/json"},
        timeout=15,
    ).json()["access_token"]

    from app.services import projects as proj_svc, artifacts as art_svc
    project = proj_svc.create(user_id, name="MCP smoke", icon=None, entry_type="fresh_idea")
    pid = project["id"]
    art_svc.upsert_prd(
        pid,
        "# PRD\n\n## Overview\nMeal-tracker app.\n\n## Auth\nEmail + password login. "
        "Lower-case-normalize emails on insert. Sessions persist 14 days.\n",
    )
    sprint = art_svc.create_sprint(pid, number=1, name="Sprint 1", subtitle="MVP")
    task = art_svc.create_task(
        project_id=pid, sprint_id=sprint["id"],
        display_id="t1", title="Build login",
        goal="Email + password auth that works",
        description="Implement login with email + password using Supabase Auth.",
        acceptance=["User can sign up", "User can sign in", "Sessions persist"],
        prd_context="Auth section of PRD",
    )

    api_port = _free_port()
    env = {**os.environ, "API_PORT": str(api_port)}
    api_cmd = [sys.executable, "-m", "uvicorn", "main:app",
               "--host", "127.0.0.1", "--port", str(api_port), "--log-level", "warning"]

    with _spawn(api_cmd, env=env, cwd=str(_API_DIR),
                ready_url=f"http://127.0.0.1:{api_port}/health", timeout=60):
        yield {
            "user_id": user_id, "project_id": pid,
            "task_id": task["id"], "task_display": task["display_id"],
            "token": token, "api_port": api_port,
        }

    proj_svc.delete(user_id, pid)
    httpx.delete(
        f"{sb}/auth/v1/admin/users/{user_id}",
        headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
        timeout=15,
    )


@pytest.fixture(scope="module")
def mcp_server(setup):
    """Reload the MCP server module with env vars pointing at our test api +
    project + token. We then call the tool functions directly."""
    os.environ["PRODUCTSENSE_API_URL"] = f"http://127.0.0.1:{setup['api_port']}"
    os.environ["PRODUCTSENSE_PROJECT_ID"] = setup["project_id"]
    os.environ["PRODUCTSENSE_TOKEN"] = setup["token"]

    # Make sure the apps/mcp dir is importable
    sys.path.insert(0, str(_MCP_DIR))
    if "server" in sys.modules:
        importlib.reload(sys.modules["server"])
    import server as mcp_server_mod
    return mcp_server_mod


@pytest.mark.asyncio
async def test_dummy_agent_full_workflow(setup, mcp_server):
    """Coding agent calls each MCP tool in order, end-to-end."""
    pid = setup["project_id"]
    task_display = setup["task_display"]
    task_uuid = setup["task_id"]

    # 1. Read context — should see seeded task
    ctx = await mcp_server.get_session_context()
    assert ctx["project_id"] == pid
    next_unblocked = [t["id"] for t in ctx["next_unblocked_tasks"]]
    assert task_uuid in next_unblocked, f"task not in unblocked: {next_unblocked}"
    print(f"[MCP] context.next_unblocked={[t['display_id'] for t in ctx['next_unblocked_tasks']]}")

    # 2. List tasks (filter)
    todo = await mcp_server.list_tasks(status="todo")
    assert any(t["id"] == task_uuid for t in todo)

    # 3. Get task spec by display_id
    one = await mcp_server.get_task(task_display)
    assert one["title"] == "Build login"

    # 4. Mark in_progress with a note
    upd = await mcp_server.update_task_status(task_display, "in_progress",
                                              notes="Picked up by dummy agent")
    assert upd["task"]["status"] == "in_progress"

    # 5. Log files touched
    files1 = await mcp_server.log_files_touched(task_display, ["src/Login.tsx"])
    assert "Login.tsx" in str(files1["task"]["files_touched"])

    # 6. Agent-with-user decision (resolved in IDE)
    dec = await mcp_server.log_decision(
        task_display, "agent_with_user",
        title="Email casing",
        detail="Normalising emails to lowercase at insert.",
        why="Avoid duplicate accounts via Gmail+ aliases",
    )
    assert dec["decision"]["display_id"].startswith("D-")

    # 7. Ask Maya for clarification — slowest call (real Maya invocation)
    print("[MCP] calling request_clarification (real Maya call)...")
    clar = await mcp_server.request_clarification(
        task_display,
        "Should login also offer magic-link alongside password, or password only?",
    )
    print(f"[MCP] clarification result: {clar}")
    assert clar.get("tier") in (1, 3), f"unexpected tier: {clar}"

    # 8. Complete the task
    done = await mcp_server.complete_task(
        task_display,
        "Implemented email/password login via Supabase Auth.",
        ["src/pages/Login.tsx", "src/lib/supabase.ts"],
    )
    assert done["task"]["status"] == "done"

    # 9. Verify DB state directly (cross-check)
    from app.services import artifacts
    final = artifacts.get_task(task_uuid)
    assert final["status"] == "done"
    assert "Login.tsx" in str(final["files_touched"])
    decisions = artifacts.list_decisions(pid)
    assert any(d["title"] == "Email casing" for d in decisions)


@pytest.mark.asyncio
async def test_dummy_agent_input_validation(setup, mcp_server):
    """Tools that get bad inputs should return isError, not crash."""
    bad_status = await mcp_server.update_task_status(setup["task_display"], "blocked")
    assert bad_status.get("isError") is True

    bad_decision = await mcp_server.log_decision(
        None, "maya_autonomous",  # reserved for the orchestrator, not the agent
        title="x", detail="y", why="z",
    )
    assert bad_decision.get("isError") is True

    short_q = await mcp_server.request_clarification(setup["task_display"], "?")
    assert short_q.get("isError") is True


def test_mcp_origin_validation(mcp_server):
    """Bad Origin header should be rejected with HTTP 403 by the ASGI wrapper.

    We exercise the wrapper through Starlette's TestClient (no subprocess)."""
    from fastapi.testclient import TestClient
    client = TestClient(mcp_server.app)
    r = client.get("/mcp", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403


def test_mcp_tools_registered(mcp_server):
    """Server should expose the documented coding-agent tool surface."""
    tools = mcp_server.server._tool_manager._tools
    expected = {
        "get_session_context", "list_tasks", "get_task",
        "update_task_status", "complete_task", "log_files_touched",
        "log_decision", "request_clarification",
        "get_decisions_log", "get_guardrails",
    }
    assert expected.issubset(set(tools.keys()))
