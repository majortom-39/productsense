"""Asset ingestor framework.

Each ingestor takes raw input (bytes / a fetched repo / a URL) and returns
an `IngestResult` with a markdown digest capped at MAX_DIGEST_TOKENS.

Maya never invokes these. The asset service dispatches to the right one
based on mime type / source kind when a founder attaches something.
"""
from .base import Ingestor, IngestResult, MAX_DIGEST_TOKENS, approx_token_count, truncate_to_tokens
from .text import TextIngestor
from .pdf import PdfIngestor
from .code import CodeIngestor
from .csv_ import CsvIngestor
from .image import ImageIngestor

__all__ = [
    "Ingestor",
    "IngestResult",
    "MAX_DIGEST_TOKENS",
    "approx_token_count",
    "truncate_to_tokens",
    "TextIngestor",
    "PdfIngestor",
    "CodeIngestor",
    "CsvIngestor",
    "ImageIngestor",
]
