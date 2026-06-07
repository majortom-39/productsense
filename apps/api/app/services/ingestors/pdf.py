"""PDF ingestor.

Uses pypdf to extract text page-by-page. We chunk by page so the digest
header lists section/page structure (useful for Maya to ask "what does
page 4 say"), and so truncation falls on natural boundaries.

For scanned/image-based PDFs (no extractable text), we fall back to a
metadata-only digest noting the page count and that OCR would be needed.
"""
from __future__ import annotations

import io
from typing import Optional

from .base import Ingestor, IngestResult, truncate_to_tokens, approx_token_count


class PdfIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        try:
            from pypdf import PdfReader
        except ImportError as e:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(PDF support unavailable: {e})_",
                error=str(e),
            )

        try:
            reader = PdfReader(io.BytesIO(content))
        except Exception as e:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(could not parse PDF: {str(e)[:160]})_",
                error=str(e)[:300],
            )

        n_pages = len(reader.pages)
        sections: list[str] = []
        char_count = 0

        for i, page in enumerate(reader.pages):
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception:
                page_text = ""
            if not page_text:
                continue
            sections.append(f"## Page {i + 1}\n\n{page_text}")
            char_count += len(page_text)

        if not sections:
            # Image-only or unparseable PDF
            return IngestResult(
                digest_md=(
                    f"# {display_name}\n\n"
                    f"_PDF · {n_pages} pages · no extractable text "
                    "(likely scanned or image-only). OCR not yet supported._"
                ),
                metadata={"n_pages": n_pages, "ocr_needed": True},
                error="No extractable text",
            )

        header = (
            f"# {display_name}\n\n"
            f"_Attached PDF · {n_pages} pages · {char_count:,} chars extracted_\n\n"
        )
        body = truncate_to_tokens(header + "\n\n".join(sections))

        return IngestResult(
            digest_md=body,
            metadata={
                "n_pages": n_pages,
                "extracted_chars": char_count,
                "approx_tokens": approx_token_count("\n\n".join(sections)),
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        if mime == "application/pdf":
            return True
        return name.lower().endswith(".pdf")
