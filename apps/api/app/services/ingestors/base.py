"""Ingestor base protocol + shared token helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


# Per-asset digest cap. Maya's total context layer (PRD + decisions +
# assets) is capped at ~8000 tokens in maya.py; per-asset 3000 leaves
# room for 2-3 substantial assets without crowding the conversation.
MAX_DIGEST_TOKENS = 3000

# Rough chars-per-token for English text. Vertex's tokenizer averages
# ~4 chars/token for prose; we use 4 as a conservative estimate.
# (We don't want to call Vertex's tokenizer per ingest — it's network.)
_CHARS_PER_TOKEN = 4


def approx_token_count(text: str) -> int:
    """Cheap, network-free token estimate.

    Errs on the high side so we under-fill the budget rather than overflow.
    Used for capping per-asset digests and the total context layer.
    """
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def truncate_to_tokens(text: str, max_tokens: int = MAX_DIGEST_TOKENS) -> str:
    """Truncate text so its approx token count is <= max_tokens.

    Truncation hits a paragraph boundary when possible (looks back for a
    \\n\\n in the last 200 chars), otherwise a sentence boundary, otherwise
    a hard char-limit cut. A footer notes the truncation so Maya knows the
    digest wasn't complete.
    """
    if approx_token_count(text) <= max_tokens:
        return text

    char_limit = max_tokens * _CHARS_PER_TOKEN
    candidate = text[:char_limit]

    # Prefer a paragraph break near the end
    para_break = candidate.rfind("\n\n", char_limit - 200, char_limit)
    if para_break != -1:
        candidate = candidate[:para_break]
    else:
        # Sentence boundary fallback
        for stop in (". ", "! ", "? ", "\n"):
            sentence_break = candidate.rfind(stop, char_limit - 200, char_limit)
            if sentence_break != -1:
                candidate = candidate[: sentence_break + 1]
                break

    return candidate.rstrip() + "\n\n_[Digest truncated to fit context budget.]_"


@dataclass
class IngestResult:
    """What an ingestor returns to the asset service.

    digest_md: markdown body to store in `project_assets.digest_md`.
    metadata:   ingestor-specific structured info (page count, line count,
                file types detected, etc.). Stored verbatim on the row.
    error:      non-None means ingestion failed; digest_md may be partial.
    """
    digest_md: str
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def digest_tokens(self) -> int:
        return approx_token_count(self.digest_md)


class Ingestor(Protocol):
    """Common shape every ingestor implements.

    `ingest` is awaitable so ingestors can call Vertex / network APIs
    (Image captioning, repo fetches, etc.).
    """

    async def ingest(self, *, content: bytes, display_name: str, mime_type: Optional[str]) -> IngestResult:
        ...
