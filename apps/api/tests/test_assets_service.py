"""Asset service tests — CRUD + dispatcher + Maya context loader.

Uses an in-memory FakeDB modeled on test_dynamic_artifacts.py's pattern.
The dispatcher is tested by name-only routing (each cls.handles); the
end-to-end ingest path is verified by stubbing a small ingestor and
asserting the row transitions pending → processing → ready.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest


# ─── Reused FakeDB pattern ────────────────────────────────────────────────


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
        self._is_null_filter = None
        self._select_cols = "*"
        self._maybe_single = False
        self._order_col = None
        self._order_desc = False

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def select(self, cols="*"):
        self._op = "select"
        self._select_cols = cols
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def is_(self, col, val):
        if val == "null":
            self._is_null_filter = col
        return self

    def order(self, col, *, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, _n):
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

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
            if self._is_null_filter:
                rows = [r for r in rows if r.get(self._is_null_filter) is None]
            if self._order_col:
                rows.sort(key=lambda r: r.get(self._order_col) or "", reverse=self._order_desc)
            if self._maybe_single:
                return FakeResult(rows[0] if rows else None)
            return FakeResult([dict(r) for r in rows])
        if self._op == "update":
            target = None
            for col, val in self._filters:
                if col == "id":
                    target = store.get(val)
                    break
            if target is None:
                return FakeResult([])
            target.update(self._payload or {})
            return FakeResult([dict(target)])
        return FakeResult([])


class FakeDB:
    def __init__(self):
        self.project_assets: dict[str, dict] = {}
        self._counter = 0

    def _next_id(self):
        self._counter += 1
        return f"asset-{self._counter}"

    def _store(self, name):
        if name == "project_assets":
            return self.project_assets
        raise KeyError(name)

    def table(self, name):
        return FakeTable(self, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    from app.services import assets as a_mod
    monkeypatch.setattr(a_mod, "require_admin", lambda: db)
    return db


# ─── Dispatcher routing ───────────────────────────────────────────────────


def test_dispatcher_routes_to_image_ingestor():
    from app.services.assets import _pick_ingestor
    from app.services.ingestors import ImageIngestor
    assert isinstance(_pick_ingestor("image/png", "shot.png"), ImageIngestor)


def test_dispatcher_routes_to_pdf_ingestor():
    from app.services.assets import _pick_ingestor
    from app.services.ingestors import PdfIngestor
    assert isinstance(_pick_ingestor("application/pdf", "spec.pdf"), PdfIngestor)


def test_dispatcher_routes_to_csv_ingestor():
    from app.services.assets import _pick_ingestor
    from app.services.ingestors import CsvIngestor
    assert isinstance(_pick_ingestor("text/csv", "feedback.csv"), CsvIngestor)


def test_dispatcher_routes_to_code_ingestor():
    from app.services.assets import _pick_ingestor
    from app.services.ingestors import CodeIngestor
    assert isinstance(_pick_ingestor(None, "App.tsx"), CodeIngestor)


def test_dispatcher_falls_back_to_text():
    from app.services.assets import _pick_ingestor
    from app.services.ingestors import TextIngestor
    assert isinstance(_pick_ingestor(None, "mystery.bin"), TextIngestor)


# ─── CRUD ─────────────────────────────────────────────────────────────────


def test_create_inserts_pending_row(fake_db):
    from app.services import assets
    row = assets.create(
        project_id="proj-1",
        asset_type="file",
        source_kind="upload",
        display_name="prd.md",
        mime_type="text/markdown",
        size_bytes=1234,
    )
    assert row["status"] == "pending"
    assert row["display_name"] == "prd.md"


def test_list_excludes_deleted(fake_db):
    from app.services import assets
    a = assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload", display_name="a.md",
    )
    assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload", display_name="b.md",
    )
    assets.delete(a["id"])
    live = assets.list_for_project("proj-1")
    names = {r["display_name"] for r in live}
    assert names == {"b.md"}


def test_delete_is_soft(fake_db):
    from app.services import assets
    a = assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload", display_name="x.md",
    )
    out = assets.delete(a["id"])
    assert out.get("deleted_at") is not None


# ─── End-to-end inline ingest ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_file_inline_transitions_to_ready(fake_db):
    """Upload a markdown asset and verify the row ends in 'ready' with a digest."""
    from app.services import assets

    row = assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload",
        display_name="brief.md", mime_type="text/markdown",
    )
    await assets.ingest_file_inline(
        asset_id=row["id"],
        content=b"# Brief\n\nBuild a fridge tracker.\n",
        display_name="brief.md",
        mime_type="text/markdown",
    )
    final = assets.get(row["id"])
    assert final["status"] == "ready"
    assert "fridge tracker" in final["digest_md"]
    assert final["digest_tokens"] > 0


@pytest.mark.asyncio
async def test_ingest_file_inline_records_errors_cleanly(fake_db, monkeypatch):
    """If the ingestor raises, the row ends in 'error' with error_text set."""
    from app.services import assets, ingestors

    class BoomIngestor:
        async def ingest(self, *, content, display_name, mime_type):
            raise RuntimeError("planned failure")

    monkeypatch.setattr(assets, "_pick_ingestor", lambda *a, **k: BoomIngestor())

    row = assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload",
        display_name="bad.md", mime_type="text/markdown",
    )
    await assets.ingest_file_inline(
        asset_id=row["id"], content=b"x", display_name="bad.md", mime_type="text/markdown",
    )
    final = assets.get(row["id"])
    assert final["status"] == "error"
    assert "planned failure" in (final.get("error_text") or "")


# ─── Maya context loader ──────────────────────────────────────────────────


def test_load_digests_for_maya_emits_block_when_assets_present(fake_db):
    from app.services import assets

    a = assets.create(
        project_id="proj-1", asset_type="file", source_kind="upload",
        display_name="prd.md",
    )
    assets.update(a["id"], status="ready", digest_md="# prd.md\n\nThe spec.", digest_tokens=20)

    block = assets.load_digests_for_maya("proj-1")
    assert "Project context layer" in block
    assert "The spec." in block


def test_load_digests_for_maya_skips_pending_and_deleted(fake_db):
    from app.services import assets

    a1 = assets.create(project_id="proj-1", asset_type="file", source_kind="upload", display_name="a.md")
    assets.update(a1["id"], status="ready", digest_md="ready content", digest_tokens=5)

    a2 = assets.create(project_id="proj-1", asset_type="file", source_kind="upload", display_name="b.md")
    # leave a2 in 'pending'

    a3 = assets.create(project_id="proj-1", asset_type="file", source_kind="upload", display_name="c.md")
    assets.update(a3["id"], status="ready", digest_md="deleted content", digest_tokens=5)
    assets.delete(a3["id"])

    block = assets.load_digests_for_maya("proj-1")
    assert "ready content" in block
    assert "deleted content" not in block
    # Nothing inserts 'pending' into the block
    assert "b.md" not in block


def test_load_digests_for_maya_respects_budget(fake_db):
    """When digests exceed the budget, newest-first wins and a footer note
    explains how many were dropped."""
    from app.services import assets

    # Three assets, each costing 600 tokens; budget of 1000 fits one
    for i in range(3):
        a = assets.create(
            project_id="proj-1", asset_type="file", source_kind="upload", display_name=f"a{i}.md",
        )
        assets.update(a["id"], status="ready", digest_md=f"content {i}", digest_tokens=600)

    block = assets.load_digests_for_maya("proj-1", budget_tokens=1000)
    assert "additional asset" in block        # truncation footer fired
    # Should NOT contain all three contents — at least one was skipped
    fits = sum(f"content {i}" in block for i in range(3))
    assert fits < 3


def test_load_digests_for_maya_returns_empty_when_no_assets(fake_db):
    from app.services import assets
    assert assets.load_digests_for_maya("empty-project") == ""
