"""Chat-model factory for the Deep Agents stack.

One place to build a Gemini chat model. Reads model + thinking assignments from
`settings`, so the live configuration (including .env overrides) is honored 1:1 —
this module never picks a model itself.

Routes the google-genai SDK through Vertex AI (ADC auth), not the public Gemini
API. Uses the non-deprecated `ChatGoogleGenerativeAI` (langchain-google-genai 4.x).
"""
from __future__ import annotations

import os

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings

# Send all google-genai traffic to Vertex AI. Must be set before any client is
# constructed. ADC supplies credentials (gcloud auth application-default login).
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

# Generous output ceiling. Gemini counts thinking tokens against this budget, so
# we keep it high to avoid truncated/empty completions on deep-thinking turns.
DEFAULT_MAX_OUTPUT_TOKENS = 8192


def _thinking_budget(thinking_level: str | None) -> int:
    """Map a thinking level to a google-genai `thinking_budget`.

    - A level set (HIGH / MEDIUM / LOW) -> -1 (dynamic; the model decides how
      much to think).
    - None -> 0 (extended thinking off, for the fast formulaic agents).
    """
    return -1 if thinking_level else 0


def build_chat_model(
    model: str,
    thinking_level: str | None = None,
    *,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> ChatGoogleGenerativeAI:
    """Build a Vertex-backed Gemini chat model."""
    return ChatGoogleGenerativeAI(
        model=model,
        project=settings.gcp_project_id,
        location=settings.vertex_location,
        thinking_budget=_thinking_budget(thinking_level),
        max_output_tokens=max_output_tokens,
    )


def build_maya_model() -> ChatGoogleGenerativeAI:
    """Maya's coordinator model, per live settings."""
    return build_chat_model(settings.maya_model, settings.maya_thinking_level)
