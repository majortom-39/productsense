"""GitHub client + repo ingestion tests.

All HTTP calls are mocked; the database is mocked through a fake_db
fixture. We assert:
  - encrypt/decrypt round-trip works (with and without a key)
  - OAuth exchange + save_connection writes the right row
  - ingest_repo builds a digest from a mocked tree + key files
  - Repo ingestion handles errors cleanly (status=error, error_text set)
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest


# ─── Reuse the FakeDB pattern for asset + connection storage ──────────────


class FakeResult:
    def __init__(self, data: Any):
        self.data = data


class FakeTable:
    def __init__(self, db, name):
        self.db = db
        self.name = name
        self._op = None
        self._payload = None
        self._filters = []
        self._is_null = None
        self._maybe_single = False
        self._order_col = None
        self._order_desc = False

    def insert(self, payload):
        self._op = "insert"; self._payload = payload; return self

    def select(self, _cols="*"):
        self._op = "select"; return self

    def update(self, payload):
        self._op = "update"; self._payload = payload; return self

    def delete(self):
        self._op = "delete"; return self

    def eq(self, col, val):
        self._filters.append((col, val)); return self

    def is_(self, col, val):
        if val == "null": self._is_null = col
        return self

    def order(self, col, *, desc=False):
        self._order_col = col; self._order_desc = desc; return self

    def limit(self, _n): return self

    def maybe_single(self):
        self._maybe_single = True; return self

    def execute(self):
        store = self.db._store(self.name)
        if self._op == "insert":
            row = {"id": self.db._next_id(), **(self._payload or {})}
            store[row["id"]] = row
            return FakeResult([dict(row)])
        if self._op == "select":
            rows = list(store.values())
            for col, val in self._filters:
                rows = [r for r in rows if r.get(col) == val]
            if self._is_null:
                rows = [r for r in rows if r.get(self._is_null) is None]
            if self._order_col:
                rows.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
            if self._maybe_single:
                return FakeResult(rows[0] if rows else None)
            return FakeResult([dict(r) for r in rows])
        if self._op == "update":
            target = None
            for col, val in self._filters:
                if col == "id":
                    target = store.get(val); break
            if target is None:
                # fallback: update by any single eq (e.g. project_id for repo link)
                for col, val in self._filters:
                    for r in store.values():
                        if r.get(col) == val:
                            target = r; break
                    if target: break
            if target is None: return FakeResult([])
            target.update(self._payload or {})
            return FakeResult([dict(target)])
        if self._op == "delete":
            to_drop: list[str] = []
            for k, r in list(store.items()):
                if all(r.get(c) == v for c, v in self._filters):
                    to_drop.append(k)
            for k in to_drop:
                del store[k]
            return FakeResult([])
        return FakeResult([])


class FakeDB:
    def __init__(self):
        self.github_connections: dict[str, dict] = {}
        self.project_assets: dict[str, dict] = {}
        self.project_repo_links: dict[str, dict] = {}
        self._counter = 0

    def _next_id(self):
        self._counter += 1
        return f"id-{self._counter}"

    def _store(self, name):
        return {
            "github_connections": self.github_connections,
            "project_assets": self.project_assets,
            "project_repo_links": self.project_repo_links,
        }[name]

    def table(self, name):
        return FakeTable(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    from app.services import github_client, assets as a_mod
    monkeypatch.setattr(github_client, "require_admin", lambda: db)
    monkeypatch.setattr(a_mod, "require_admin", lambda: db)
    return db


# ─── Token encryption ─────────────────────────────────────────────────────


def test_encrypt_round_trip_with_key(monkeypatch):
    from cryptography.fernet import Fernet
    from app.config import settings
    from app.services import github_client

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "asset_encryption_key", key)
    plaintext = "ghp_fake_token_123"
    enc = github_client.encrypt_token(plaintext)
    assert enc != plaintext
    assert github_client.decrypt_token(enc) == plaintext


def test_encrypt_no_key_is_passthrough(monkeypatch):
    from app.config import settings
    from app.services import github_client

    monkeypatch.setattr(settings, "asset_encryption_key", "")
    plaintext = "ghp_dev_token"
    assert github_client.encrypt_token(plaintext) == plaintext
    assert github_client.decrypt_token(plaintext) == plaintext


# ─── OAuth flow (mocked HTTP) ─────────────────────────────────────────────


def _mock_responses(monkeypatch, by_url: dict):
    """Patch httpx.AsyncClient so .get/.post return prebuilt responses by URL."""
    class FakeResponse:
        def __init__(self, status_code, json_body):
            self.status_code = status_code
            self._json = json_body
            self.text = str(json_body)

        def json(self):
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"{self.status_code}", request=None, response=None,  # type: ignore[arg-type]
                )

    class FakeClient:
        def __init__(self, *_a, **_kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **_kw):
            for prefix, body in by_url.items():
                if url.startswith(prefix):
                    return FakeResponse(200, body)
            return FakeResponse(404, {"error": "no match"})
        async def get(self, url, **_kw):
            for prefix, body in by_url.items():
                if url.startswith(prefix):
                    return FakeResponse(200, body)
            return FakeResponse(404, {"error": "no match"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)


@pytest.mark.asyncio
async def test_exchange_code_for_token_returns_payload(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "github_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "csec")
    _mock_responses(monkeypatch, {
        "https://github.com/login/oauth/access_token": {
            "access_token": "ghp_test", "scope": "repo", "token_type": "bearer",
        },
    })

    from app.services import github_client
    out = await github_client.exchange_code_for_token("abc123")
    assert out["access_token"] == "ghp_test"


@pytest.mark.asyncio
async def test_exchange_code_raises_when_oauth_unconfigured(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "github_oauth_client_id", "")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "")
    from app.services import github_client
    with pytest.raises(RuntimeError, match="not configured"):
        await github_client.exchange_code_for_token("anything")


@pytest.mark.asyncio
async def test_save_connection_persists_login(monkeypatch, fake_db):
    from app.config import settings
    monkeypatch.setattr(settings, "github_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "csec")
    monkeypatch.setattr(settings, "asset_encryption_key", "")
    _mock_responses(monkeypatch, {
        "https://github.com/login/oauth/access_token": {
            "access_token": "ghp_user_token", "scope": "repo,read:user",
        },
        "https://api.github.com/user": {"login": "octocat"},
    })

    from app.services import github_client
    out = await github_client.save_connection(user_id="user-1", code="x")
    assert out["github_user_login"] == "octocat"
    # Token isn't returned to the API caller
    assert "access_token_enc" not in out
    # But it IS stored
    assert len(fake_db.github_connections) == 1


@pytest.mark.asyncio
async def test_save_connection_upserts_on_repeat(monkeypatch, fake_db):
    from app.config import settings
    monkeypatch.setattr(settings, "github_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "github_oauth_client_secret", "csec")
    monkeypatch.setattr(settings, "asset_encryption_key", "")
    _mock_responses(monkeypatch, {
        "https://github.com/login/oauth/access_token": {"access_token": "tok1"},
        "https://api.github.com/user": {"login": "octocat"},
    })

    from app.services import github_client
    await github_client.save_connection(user_id="user-1", code="x")
    await github_client.save_connection(user_id="user-1", code="y")
    # Still one row, not two
    assert len(fake_db.github_connections) == 1


# ─── Repo digest builder ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_repo_builds_digest_and_links(monkeypatch, fake_db):
    from app.config import settings
    monkeypatch.setattr(settings, "asset_encryption_key", "")
    # Seed a connection
    fake_db.github_connections["conn-1"] = {
        "id": "conn-1", "user_id": "user-1", "github_user_login": "octocat",
        "access_token_enc": "plain-token",
    }
    _mock_responses(monkeypatch, {
        "https://api.github.com/repos/octocat/hello/git/trees/main": {
            "tree": [
                {"path": "README.md", "type": "blob", "size": 100},
                {"path": "src/index.ts", "type": "blob", "size": 200},
                {"path": "src/components/Foo.tsx", "type": "blob", "size": 80},
                {"path": "package.json", "type": "blob", "size": 50},
            ],
        },
        "https://api.github.com/repos/octocat/hello/contents/README.md": {
            "encoding": "base64",
            "content": _b64("# Hello Octocat\n\nA small repo.\n"),
        },
        "https://api.github.com/repos/octocat/hello/contents/package.json": {
            "encoding": "base64",
            "content": _b64('{"name": "hello", "dependencies": {"react": "18"}}'),
        },
    })

    from app.services import github_client
    asset = await github_client.ingest_repo(
        project_id="proj-1",
        connection_id="conn-1",
        repo_full_name="octocat/hello",
        branch="main",
    )
    assert asset["status"] == "ready"
    assert "Hello Octocat" in asset["digest_md"]
    assert "package.json" in asset["digest_md"]
    assert asset["asset_type"] == "repo"
    # A link row exists pointing at the asset
    links = list(fake_db.project_repo_links.values())
    assert len(links) == 1
    assert links[0]["repo_full_name"] == "octocat/hello"
    assert links[0]["asset_id"] == asset["id"]


@pytest.mark.asyncio
async def test_ingest_repo_marks_error_on_api_failure(monkeypatch, fake_db):
    from app.config import settings
    monkeypatch.setattr(settings, "asset_encryption_key", "")
    fake_db.github_connections["conn-1"] = {
        "id": "conn-1", "user_id": "user-1", "github_user_login": "octocat",
        "access_token_enc": "plain-token",
    }

    # No URL mapping → all responses are 404 → raise_for_status fails
    _mock_responses(monkeypatch, {})

    from app.services import github_client
    with pytest.raises(Exception):
        await github_client.ingest_repo(
            project_id="proj-1",
            connection_id="conn-1",
            repo_full_name="octocat/missing",
            branch="main",
        )

    # And the asset row landed in 'error' state
    assets = list(fake_db.project_assets.values())
    assert len(assets) == 1
    assert assets[0]["status"] == "error"
    assert assets[0]["error_text"]


def _b64(s: str) -> str:
    import base64
    return base64.b64encode(s.encode("utf-8")).decode("ascii")
