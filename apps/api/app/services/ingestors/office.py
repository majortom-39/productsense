"""Office-document ingestor — Word / PowerPoint / Excel (+ HTML) via MarkItDown.

MarkItDown converts the file to clean LLM-readable markdown; we wrap it in the
same digest format the other ingestors produce. Deliberately installed lean —
`markitdown[docx,pptx,xlsx]` only. PDFs keep the existing pypdf ingestor and
images keep the Gemini-vision ingestor (the model reads pictures better than
any converter), so this covers exactly the formats nothing else handled.

The extracted text is founder-supplied DATA for Maya to read — never
instructions. The context-layer header (assets.load_digests_for_maya) and the
session injection both carry that framing.
"""
from __future__ import annotations

import io
from typing import Optional

from .base import Ingestor, IngestResult, truncate_to_tokens, approx_token_count


_EXT_LABEL = {
    ".docx": "Word document",
    ".pptx": "PowerPoint deck",
    ".xlsx": "Excel sheet",
    ".html": "HTML page",
    ".htm": "HTML page",
}

_OFFICE_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/html": ".html",
}


def _ext_of(mime: Optional[str], name: str) -> Optional[str]:
    if mime and mime in _OFFICE_MIMES:
        return _OFFICE_MIMES[mime]
    lower = name.lower()
    for ext in _EXT_LABEL:
        if lower.endswith(ext):
            return ext
    return None


class OfficeIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        try:
            from markitdown import MarkItDown
        except ImportError as e:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(office-document support unavailable: {e})_",
                error=str(e),
            )

        ext = _ext_of(mime_type, display_name) or ".docx"
        try:
            # enable_plugins=False keeps conversion local + deterministic; the
            # extension hint routes MarkItDown to the right converter when the
            # browser sent a generic mime type.
            md = MarkItDown(enable_plugins=False)
            result = md.convert_stream(io.BytesIO(content), file_extension=ext)
            text = (result.text_content or "").strip()
        except Exception as e:
            return IngestResult(
                digest_md=(
                    f"# {display_name}\n\n"
                    f"_(could not convert {_EXT_LABEL.get(ext, 'document')}: {str(e)[:160]})_"
                ),
                error=str(e)[:300],
            )

        if not text:
            return IngestResult(
                digest_md=(
                    f"# {display_name}\n\n"
                    f"_{_EXT_LABEL.get(ext, 'Document')} · no extractable text._"
                ),
                metadata={"ext": ext, "size_bytes": len(content)},
                error="No extractable text",
            )

        header = (
            f"# {display_name}\n\n"
            f"_Attached {_EXT_LABEL.get(ext, 'document')} · {len(text):,} chars extracted_\n\n"
        )
        return IngestResult(
            digest_md=truncate_to_tokens(header + text),
            metadata={
                "ext": ext,
                "size_bytes": len(content),
                "extracted_chars": len(text),
                "approx_tokens": approx_token_count(text),
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        return _ext_of(mime, name) is not None
