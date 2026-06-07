"""Live smoke against real Supabase. Creates a temp user, generates a JWT,
then exercises projects CRUD + artifact reads through the FastAPI app.

Run with:
    cd apps/api && python -m pytest tests/smoke_live.py -v -s

Skips automatically if .env doesn't have a real service role key.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from app.config import settings


pytestmark = pytest.mark.skipif(
    not settings.supabase_service_role_key
    or settings.supabase_service_role_key.startswith("test-"),
    reason="Real SUPABASE_SERVICE_ROLE_KEY required (not the conftest stub)",
)


@pytest.fixture(scope="module")
def temp_user():
    """Create a temp user via Supabase Admin API; tear down after."""
    sb_url = settings.supabase_url
    service_key = settings.supabase_service_role_key
    email = f"test-{uuid.uuid4().hex[:8]}@productsense.test"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    # 1. Create the user with email_confirm so we can sign in immediately
    r = httpx.post(
        f"{sb_url}/auth/v1/admin/users",
        json={"email": email, "password": "TestPass123!", "email_confirm": True},
        headers=headers,
        timeout=15,
    )
    assert r.status_code in (200, 201), f"create user failed: {r.status_code} {r.text}"
    user = r.json()
    user_id = user["id"]

    # 2. Sign in to get an access token
    anon_key = settings.supabase_anon_key
    r = httpx.post(
        f"{sb_url}/auth/v1/token?grant_type=password",
        json={"email": email, "password": "TestPass123!"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code == 200, f"signin failed: {r.status_code} {r.text}"
    access_token = r.json()["access_token"]

    yield {"id": user_id, "email": email, "access_token": access_token}

    # 3. Cleanup
    httpx.delete(
        f"{sb_url}/auth/v1/admin/users/{user_id}",
        headers=headers,
        timeout=15,
    )


def test_unauth_returns_401():
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)
    r = client.get("/projects")
    assert r.status_code == 401


def test_full_project_lifecycle(temp_user):
    from fastapi.testclient import TestClient
    import main
    client = TestClient(main.app)
    h = {"Authorization": f"Bearer {temp_user['access_token']}"}

    # Create
    r = client.post("/projects", json={"name": "Smoke project"}, headers=h)
    assert r.status_code == 201, r.text
    project = r.json()
    pid = project["id"]
    assert project["user_id"] == temp_user["id"]

    # List — should include it
    r = client.get("/projects", headers=h)
    assert r.status_code == 200
    assert any(p["id"] == pid for p in r.json())

    # Get one
    r = client.get(f"/projects/{pid}", headers=h)
    assert r.status_code == 200

    # Other user can't see it (use a fresh token absent any user)
    r = client.get(f"/projects/{pid}", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401

    # Empty PRD / tasks / decisions / research return their empty shapes
    assert client.get(f"/projects/{pid}/prd", headers=h).json() == {"prd": None}
    assert client.get(f"/projects/{pid}/tasks", headers=h).json() == {"tasks": []}
    assert client.get(f"/projects/{pid}/decisions", headers=h).json() == {"decisions": []}
    assert client.get(f"/projects/{pid}/research", headers=h).json() == {"research": []}

    # Delete
    r = client.delete(f"/projects/{pid}", headers=h)
    assert r.status_code == 200
    r = client.get(f"/projects/{pid}", headers=h)
    assert r.status_code == 404
