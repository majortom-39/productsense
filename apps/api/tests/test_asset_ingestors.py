"""Ingestor unit tests — pure functions, no DB or network.

We feed each ingestor a small fixture input and assert it produces a
non-empty, capped digest plus the right metadata. Image ingestor is
mocked at the gemini.call boundary so the test doesn't hit Vertex.
"""
from __future__ import annotations

import pytest

from app.services.ingestors import (
    CodeIngestor,
    CsvIngestor,
    ImageIngestor,
    PdfIngestor,
    TextIngestor,
    approx_token_count,
    truncate_to_tokens,
    MAX_DIGEST_TOKENS,
)


# ─── helpers ──────────────────────────────────────────────────────────────


def test_approx_token_count_handles_empty_and_short_text():
    assert approx_token_count("") == 0
    # Single char is at least 1 token under the conservative rounding
    assert approx_token_count("x") == 1
    # ~10 tokens for 40 chars at 4 chars/token
    assert 8 <= approx_token_count("a" * 40) <= 12


def test_truncate_to_tokens_keeps_short_text_intact():
    text = "short body"
    assert truncate_to_tokens(text) == text


def test_truncate_to_tokens_falls_back_with_marker():
    # Build a body well beyond the cap and check we get the truncation marker
    body = "paragraph.\n\n" * 5000
    out = truncate_to_tokens(body, max_tokens=200)
    assert approx_token_count(out) <= 250         # cap + small marker overhead
    assert "Digest truncated" in out


# ─── TextIngestor ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_text_ingestor_emits_digest_with_header():
    body = b"# My PRD\n\nThis is the first paragraph.\n\n## Auth\nEmail + password.\n"
    res = await TextIngestor().ingest(content=body, display_name="prd.md", mime_type="text/markdown")
    assert res.error is None
    assert "prd.md" in res.digest_md
    assert "Email + password" in res.digest_md
    assert res.metadata["heading_count"] == 2


@pytest.mark.asyncio
async def test_text_ingestor_handles_empty_file():
    res = await TextIngestor().ingest(content=b"", display_name="empty.txt", mime_type="text/plain")
    assert res.error is None
    assert res.metadata.get("empty") is True


def test_text_ingestor_handles_routes_md_and_txt():
    assert TextIngestor.handles("text/markdown", "notes.md")
    assert TextIngestor.handles(None, "scratch.txt")
    assert not TextIngestor.handles("application/pdf", "doc.pdf")


# ─── PdfIngestor ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_ingestor_extracts_text_from_minimal_pdf():
    # Build a minimal PDF in-process via pypdf so we don't ship a fixture
    from pypdf import PdfWriter
    import io
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    res = await PdfIngestor().ingest(content=buf.getvalue(), display_name="blank.pdf", mime_type="application/pdf")
    # Blank PDFs trigger the "no extractable text" branch but should NOT raise
    assert res.metadata.get("n_pages") == 1
    assert "blank.pdf" in res.digest_md


@pytest.mark.asyncio
async def test_pdf_ingestor_handles_garbage_input():
    res = await PdfIngestor().ingest(content=b"not actually a pdf", display_name="x.pdf", mime_type="application/pdf")
    assert res.error is not None
    assert "x.pdf" in res.digest_md


# ─── CodeIngestor ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_code_ingestor_extracts_python_symbols():
    body = b'''"""mod docstring."""
import os

class Foo:
    def bar(self, x):
        return x

async def baz(y):
    return y + 1
'''
    res = await CodeIngestor().ingest(content=body, display_name="mod.py", mime_type=None)
    assert res.error is None
    assert res.metadata["language"] == "Python"
    # Symbols + at least one of the head lines
    assert "class Foo" in res.digest_md
    assert "def bar" in res.digest_md
    assert "async def baz" in res.digest_md
    assert "import os" in res.digest_md


@pytest.mark.asyncio
async def test_code_ingestor_extracts_typescript_exports():
    body = b'''export const FOO = 1;
export function greet(name: string) { return "hi"; }
export class Bar { }
export interface Baz { x: number }
'''
    res = await CodeIngestor().ingest(content=body, display_name="x.ts", mime_type=None)
    assert res.metadata["language"] == "TypeScript"
    # All four kinds of exports
    for sym in ("FOO", "greet", "Bar", "Baz"):
        assert sym in res.digest_md


def test_code_ingestor_handles_routes_by_extension():
    assert CodeIngestor.handles(None, "lib.py")
    assert CodeIngestor.handles(None, "App.tsx")
    assert CodeIngestor.handles(None, "schema.sql")
    assert not CodeIngestor.handles(None, "report.pdf")


# ─── CsvIngestor ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_csv_ingestor_extracts_columns_and_sample():
    body = b"name,age,signup_at\nAlice,30,2024-01-01\nBob,25,2024-01-02\nCarol,40,2024-01-03\n"
    res = await CsvIngestor().ingest(content=body, display_name="users.csv", mime_type="text/csv")
    assert res.error is None
    assert res.metadata["n_rows"] == 3
    assert res.metadata["n_columns"] == 3
    assert res.metadata["column_names"] == ["name", "age", "signup_at"]
    # Sample contains an actual row
    assert "Alice" in res.digest_md
    # Type inferred for the age column
    assert "int" in res.metadata["column_types"][1]


@pytest.mark.asyncio
async def test_csv_ingestor_handles_empty_file():
    res = await CsvIngestor().ingest(content=b"", display_name="empty.csv", mime_type="text/csv")
    assert res.metadata.get("empty") is True


# ─── ImageIngestor (mocked Vertex) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_image_ingestor_calls_gemini_and_renders_caption(monkeypatch):
    from app.services import gemini as gemini_mod
    from app.services.ingestors import image as image_mod
    from types import SimpleNamespace

    class _Resp:
        text = "A grid of three pricing tiers labeled Free, Pro, and Team."
        candidates: list = []

    async def fake_call(**_kw):
        return _Resp()

    monkeypatch.setattr(gemini_mod, "call", fake_call)
    monkeypatch.setattr(image_mod.gemini, "call", fake_call)
    monkeypatch.setattr(gemini_mod, "extract_text", lambda r: r.text)
    monkeypatch.setattr(image_mod.gemini, "extract_text", lambda r: r.text)

    res = await ImageIngestor().ingest(
        content=b"fake-png-bytes",
        display_name="pricing.png",
        mime_type="image/png",
    )
    assert res.error is None
    assert "Free, Pro, and Team" in res.digest_md
    assert "pricing.png" in res.digest_md
    assert res.metadata["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_image_ingestor_rejects_unknown_mime():
    res = await ImageIngestor().ingest(
        content=b"x",
        display_name="weird.bmp",
        mime_type="image/x-bitmap",
    )
    assert res.error is not None
    assert "unsupported" in res.digest_md.lower()


# ─── Digest cap is enforced across all ingestors ──────────────────────────


@pytest.mark.asyncio
async def test_long_text_is_capped_at_max_tokens():
    body = ("This is a sentence. " * 20000).encode("utf-8")
    res = await TextIngestor().ingest(content=body, display_name="huge.txt", mime_type="text/plain")
    # +small overhead for the truncation marker
    assert res.digest_tokens <= MAX_DIGEST_TOKENS + 50
