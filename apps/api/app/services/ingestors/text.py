"""Text / markdown ingestor.

The simplest path: read the bytes as UTF-8, structurally summarize.
For short docs (<2000 tokens) we keep the full body. For longer ones we
prepend a Maya-friendly header that names the structure (heading count,
total length) so she can ask for specific sections.

LLM-free on purpose: most attached "context docs" are PRDs, briefs, READMEs,
or notes that don't need rewriting. Maya reads markdown natively.
"""
from __future__ import annotations

import re
from typing import Optional

from .base import Ingestor, IngestResult, approx_token_count, truncate_to_tokens


_TEXT_MIMES = {
    "text/plain", "text/markdown", "text/x-markdown",
    "text/csv",  # falls back to text if CsvIngestor isn't routed first
}


class TextIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            # Latin-1 always decodes; legible enough for most office output
            text = content.decode("latin-1", errors="replace")

        text = text.strip()
        if not text:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(empty file)_",
                metadata={"empty": True},
            )

        headings = re.findall(r"^(#+)\s+(.+)$", text, flags=re.MULTILINE)
        chars = len(text)
        approx_tokens = approx_token_count(text)

        header = (
            f"# {display_name}\n\n"
            f"_Attached document · {chars:,} chars · ~{approx_tokens:,} tokens"
            + (f" · {len(headings)} headings_" if headings else "_")
            + "\n\n"
        )

        body = truncate_to_tokens(header + text)
        return IngestResult(
            digest_md=body,
            metadata={
                "chars": chars,
                "approx_tokens": approx_tokens,
                "heading_count": len(headings),
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        if mime and mime in _TEXT_MIMES:
            return True
        return name.lower().endswith((".txt", ".md", ".markdown", ".rst"))
