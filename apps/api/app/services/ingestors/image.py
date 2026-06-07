"""Image ingestor.

Sends the image to Gemini (Flash) for a structured caption. Useful for:
  - Screenshots of competitor products
  - Sketches / whiteboard photos
  - UI mockups
  - Diagrams

Output: markdown digest with a "what's in the image" description plus
any text extracted from the screenshot (Gemini reads UI text well).
"""
from __future__ import annotations

import base64
from typing import Optional

from google.genai import types as gtypes

from app.config import settings
from app.services import gemini
from .base import Ingestor, IngestResult, truncate_to_tokens


_IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg",
    "image/webp", "image/gif",
}

_CAPTION_PROMPT = (
    "You are summarizing this image for a product manager who needs context. "
    "Describe what's in the image in plain English. If it's a UI screenshot, "
    "list the visible features, buttons, copy, and notable design choices. "
    "If it's a sketch or diagram, describe the structure. If it's a chart, "
    "describe what's being measured and the trend. Be concrete and specific. "
    "No preamble; just the description."
)


class ImageIngestor(Ingestor):
    async def ingest(
        self,
        *,
        content: bytes,
        display_name: str,
        mime_type: Optional[str],
    ) -> IngestResult:
        if not mime_type:
            # Best-effort sniff from extension
            lower = display_name.lower()
            for ext, mt in [
                (".png", "image/png"),
                (".jpg", "image/jpeg"),
                (".jpeg", "image/jpeg"),
                (".webp", "image/webp"),
                (".gif", "image/gif"),
            ]:
                if lower.endswith(ext):
                    mime_type = mt
                    break

        if not mime_type or mime_type not in _IMAGE_MIMES:
            return IngestResult(
                digest_md=f"# {display_name}\n\n_(unsupported image type: {mime_type})_",
                error=f"Unsupported mime: {mime_type}",
            )

        # Build Gemini Content with inline image data + caption prompt
        try:
            inline = gtypes.Part.from_bytes(data=content, mime_type=mime_type)
            user_part = gtypes.Content(
                role="user",
                parts=[inline, gtypes.Part.from_text(text=_CAPTION_PROMPT)],
            )
            response = await gemini.call(
                model=settings.subagent_model,
                contents=[user_part],
                max_output_tokens=1200,
            )
            caption = gemini.extract_text(response).strip()
        except Exception as e:
            return IngestResult(
                digest_md=(
                    f"# {display_name}\n\n"
                    f"_(image captioning failed: {str(e)[:160]})_"
                ),
                error=str(e)[:300],
            )

        if not caption:
            caption = "_(Gemini returned no caption.)_"

        body_md = (
            f"# {display_name}\n\n"
            f"_Attached image · {len(content):,} bytes · {mime_type}_\n\n"
            f"## What's in this image\n\n{caption}\n"
        )
        return IngestResult(
            digest_md=truncate_to_tokens(body_md),
            metadata={
                "mime_type": mime_type,
                "size_bytes": len(content),
                "caption_chars": len(caption),
            },
        )

    @classmethod
    def handles(cls, mime: Optional[str], name: str) -> bool:
        if mime and mime in _IMAGE_MIMES:
            return True
        lower = name.lower()
        return any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"))
