"""Vertex AI Gemini wrapper.

Single async entrypoint `call()` plus helpers for tool-call extraction and
content-turn construction. Handles 429 / 503 backoff. Schema-cleans tool
declarations (Gemini rejects $schema / additionalProperties / title).

Auth: Application Default Credentials. Set via:
    gcloud auth application-default login
    gcloud config set project <gcp_project_id>
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

import google.genai as genai
from google.genai import types as gtypes

from app.config import settings


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=settings.gcp_project_id,
            location=settings.vertex_location,
        )
    return _client


_BLOCKED_SCHEMA_KEYS = {"additionalProperties", "additional_properties", "$schema", "title"}


def _clean_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        if isinstance(schema, list):
            return [_clean_schema(i) for i in schema]
        return schema
    return {
        k: _clean_schema(v)
        for k, v in schema.items()
        if k not in _BLOCKED_SCHEMA_KEYS
    }


def _build_config(
    system: str,
    tool_declarations: list[gtypes.FunctionDeclaration] | None,
    thinking_level: str | None,
    thinking_budget: int | None,
    max_output_tokens: int,
    include_thoughts: bool = False,
    response_schema: Any = None,
    response_mime_type: str | None = None,
) -> gtypes.GenerateContentConfig:
    """Shared config builder for streaming + non-streaming calls.

    `response_schema` accepts either a Pydantic model class or a raw JSON
    schema dict (cleaned of Vertex-rejected keys). When set, the model is
    constrained to return JSON matching the shape — eliminating the class
    of failures where a sub-agent leaks planning prose into a string field.

    Vertex enforces `response_schema` only when `tools` is NOT set. For
    sub-agents that need research tools during a turn, schema enforcement
    is moot for that turn; callers should refinement-call once tools are
    no longer needed."""
    if thinking_level is not None:
        thinking_cfg = gtypes.ThinkingConfig(
            thinking_level=thinking_level,
            include_thoughts=include_thoughts,
        )
    else:
        thinking_cfg = gtypes.ThinkingConfig(
            thinking_budget=thinking_budget if thinking_budget is not None else -1,
            include_thoughts=include_thoughts,
        )

    config_kwargs: dict[str, Any] = {
        "max_output_tokens": max_output_tokens,
        "thinking_config": thinking_cfg,
    }
    if system:
        config_kwargs["system_instruction"] = system
    if tool_declarations:
        cleaned = [
            gtypes.FunctionDeclaration(
                name=td.name,
                description=td.description,
                parameters=_clean_schema(td.parameters) if td.parameters else None,
            )
            for td in tool_declarations
        ]
        config_kwargs["tools"] = [gtypes.Tool(function_declarations=cleaned)]
    if response_mime_type:
        config_kwargs["response_mime_type"] = response_mime_type
    if response_schema is not None:
        # Vertex accepts either a Pydantic model class OR a JSON-schema dict.
        # Clean dicts to drop keys Vertex rejects ($schema, additionalProperties, title).
        if isinstance(response_schema, dict):
            config_kwargs["response_schema"] = _clean_schema(response_schema)
        else:
            config_kwargs["response_schema"] = response_schema
    return gtypes.GenerateContentConfig(**config_kwargs)


async def call(
    model: str,
    system: str,
    contents: list[gtypes.Content],
    tool_declarations: list[gtypes.FunctionDeclaration] | None = None,
    thinking_budget: int | None = None,
    thinking_level: str | None = None,   # 'HIGH' | 'MEDIUM' | 'LOW' (Gemini 3.x only)
    max_output_tokens: int = 65535,
    log_label: str | None = None,        # optional caller hint for diagnostic logs
    response_schema: Any = None,         # Pydantic model class OR JSON-schema dict
    response_mime_type: str | None = None,  # usually "application/json" when schema set
) -> gtypes.GenerateContentResponse:
    """Single Gemini API call with retry. Returns the raw response.

    Pass EITHER `thinking_level` (Gemini 3.x — string knob) OR
    `thinking_budget` (older numeric: -1 dynamic, 0 disabled, N fixed).
    Defaults to dynamic budget if neither is set.

    On every response we log finish_reason + any prompt_feedback.block_reason
    when the model returned no text. That's the only way to diagnose the
    "agent returned empty envelope" failure mode — silent SAFETY blocks,
    MAX_TOKENS truncations, and RECITATION refusals all look identical
    from the caller's perspective without this signal.
    """
    client = get_client()
    config = _build_config(
        system, tool_declarations, thinking_level, thinking_budget,
        max_output_tokens, include_thoughts=False,
        response_schema=response_schema,
        response_mime_type=response_mime_type,
    )

    last_err: Exception | None = None
    for attempt in range(6):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            _log_unhealthy_response(response, model=model, label=log_label)
            return response
        except Exception as e:
            last_err = e
            err_str = str(e)
            if attempt >= 5:
                raise
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                m = re.search(r"retryDelay.*?(\d+)s", err_str)
                wait = int(m.group(1)) + 2 if m else min(60, 15 * (attempt + 1))
                await asyncio.sleep(wait)
                continue
            if "503" in err_str or "500" in err_str or "UNAVAILABLE" in err_str:
                await asyncio.sleep(3 * (2 ** attempt))
                continue
            raise
    raise last_err  # type: ignore[misc]


def _log_unhealthy_response(
    response: gtypes.GenerateContentResponse,
    *,
    model: str,
    label: str | None,
) -> None:
    """Print a one-line diagnostic when Gemini returns something we'd consider
    'empty' from a caller's perspective:
      - prompt-level block (block_reason set on prompt_feedback)
      - candidate finish_reason != STOP (SAFETY, MAX_TOKENS, RECITATION, OTHER)
      - candidate has no text parts AND no function_call parts
    Healthy responses stay silent so the log doesn't get noisy."""
    try:
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
        parts = (candidate.content.parts if candidate and candidate.content else []) or []
        text_chars = sum(len(getattr(p, "text", "") or "") for p in parts)
        has_fc = any(getattr(p, "function_call", None) for p in parts)

        # Coerce enum-ish reasons to readable strings without touching their enum value.
        fr_str = getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else None)
        br_str = getattr(block_reason, "name", None) or (str(block_reason) if block_reason else None)

        # Healthy = STOP and either text or a function call. Otherwise it's
        # diagnostic-worthy.
        is_healthy = (
            (fr_str in {None, "STOP", "FinishReason.STOP", "1"})
            and not br_str
            and (text_chars > 0 or has_fc)
        )
        if is_healthy:
            return

        usage = getattr(response, "usage_metadata", None)
        total_tokens = getattr(usage, "total_token_count", None) if usage else None
        prefix = f"[gemini.call] {label or model} "
        print(
            prefix
            + f"unhealthy response — finish_reason={fr_str!r} "
            + f"block_reason={br_str!r} text_chars={text_chars} "
            + f"function_calls={has_fc} total_tokens={total_tokens}"
        )
    except Exception as e:
        # Logging must never affect the call path.
        print(f"[gemini.call] log inspection failed: {e}")


# ─── Response helpers ──────────────────────────────────────────────────────

def extract_text(response: gtypes.GenerateContentResponse) -> str:
    return response.text or ""


def inspect_response(response: gtypes.GenerateContentResponse) -> dict:
    """Extract the signals a caller needs to diagnose an empty/abnormal
    response without re-walking the candidate tree. Returns:
        {
          finish_reason: str | None  ("STOP" | "SAFETY" | "MAX_TOKENS" | …)
          block_reason:  str | None  (from prompt_feedback, prompt-level block)
          has_text:      bool
          has_function_call: bool
        }
    Used to distinguish:
      - SAFETY block (surface to caller as `safety_blocked`, don't retry)
      - variance (no block, no text, finish=STOP → retry once)
      - truncation (handled by `was_max_tokens_truncated`)
    """
    try:
        prompt_feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(prompt_feedback, "block_reason", None) if prompt_feedback else None
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
        parts = (candidate.content.parts if candidate and candidate.content else []) or []
        text_chars = sum(len(getattr(p, "text", "") or "") for p in parts)
        has_fc = any(getattr(p, "function_call", None) for p in parts)
        fr_str = getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else None)
        br_str = getattr(block_reason, "name", None) or (str(block_reason) if block_reason else None)
        return {
            "finish_reason": fr_str,
            "block_reason": br_str,
            "has_text": text_chars > 0,
            "has_function_call": has_fc,
        }
    except Exception as e:
        print(f"[gemini.inspect_response] failed: {e}")
        return {"finish_reason": None, "block_reason": None, "has_text": False, "has_function_call": False}


def was_max_tokens_truncated(response: gtypes.GenerateContentResponse) -> bool:
    """True iff Gemini stopped because it hit the output-token cap.

    Detecting this lets callers short-circuit JSON parsing — the response
    is mid-stream and will not parse, dumping the raw envelope into
    downstream fields. Better to surface a clean "ran out of room" signal.
    """
    try:
        candidates = getattr(response, "candidates", None) or []
        candidate = candidates[0] if candidates else None
        finish_reason = getattr(candidate, "finish_reason", None) if candidate else None
        fr_str = getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else "")
        # Vertex SDK names the enum FinishReason.MAX_TOKENS.
        return "MAX_TOKENS" in (fr_str or "")
    except Exception:
        return False


def extract_tool_calls(
    response: gtypes.GenerateContentResponse,
) -> list[dict[str, Any]]:
    candidate = response.candidates[0] if response.candidates else None
    if not candidate or not candidate.content or not candidate.content.parts:
        return []
    return [
        {"name": p.function_call.name, "args": dict(p.function_call.args)}
        for p in candidate.content.parts
        if p.function_call is not None
    ]


def model_turn_from_response(
    response: gtypes.GenerateContentResponse,
) -> gtypes.Content | None:
    candidate = response.candidates[0] if response.candidates else None
    if not candidate or not candidate.content:
        return None
    has_fc = any(p.function_call is not None for p in candidate.content.parts)
    return candidate.content if has_fc else None


def function_response_turn(name: str, result: str) -> gtypes.Content:
    """Single function_response wrapped as a user-role Content. Use when
    only one tool was called. For multi-tool turns, prefer
    `function_responses_turn(items)` which packs all responses into one
    Content per Vertex's parallel-call protocol."""
    return gtypes.Content(
        role="user",
        parts=[gtypes.Part(
            function_response=gtypes.FunctionResponse(
                name=name,
                response={"result": result},
            )
        )],
    )


def function_responses_turn(items: list[tuple[str, str]]) -> gtypes.Content:
    """Bundle multiple function_response parts into a single user-role Content.

    Vertex requires that responses to parallel function_calls live inside ONE
    Content message — splitting them across multiple Contents triggers
    "number of function response parts must equal number of function call
    parts of the function call turn" (400 INVALID_ARGUMENT).
    """
    return gtypes.Content(
        role="user",
        parts=[
            gtypes.Part(
                function_response=gtypes.FunctionResponse(
                    name=name, response={"result": result}
                )
            )
            for name, result in items
        ],
    )


def text_turn(role: str, text: str) -> gtypes.Content:
    return gtypes.Content(role=role, parts=[gtypes.Part(text=text)])


# ─── Grounded search (fast fact-check) ───────────────────────────────────

async def grounded_search(
    query: str,
    *,
    model: str | None = None,
    max_output_tokens: int = 4096,
) -> dict:
    """Single-shot Gemini call with the built-in google_search tool enabled.

    Used by Maya's `verify` tool for ad-hoc fact-checks ("is Gemini 2.0
    really the latest Live API?" / "what's the current OpenAI Realtime
    pricing?"). Grounded search returns inline citations attached to the
    response candidate via `grounding_metadata`; we extract them into a
    flat `sources: [{title, url}]` list for the caller.

    Returns:
        {
          "finding":     str  — the model's grounded answer text,
          "sources":     [{label, url}, ...],
          "raw_queries": [str, ...]   — the actual search queries Gemini ran,
          "ok":          bool — False when the model returned nothing usable,
        }

    Failure modes are surfaced explicitly (no exceptions) so Maya can
    handle them in her reasoning (e.g. "I tried to verify but the search
    came back empty — let me re-dispatch the sub-agent instead").
    """
    chosen_model = model or settings.fast_model
    client = get_client()
    config = gtypes.GenerateContentConfig(
        tools=[gtypes.Tool(google_search=gtypes.GoogleSearch())],
        max_output_tokens=max_output_tokens,
        # Strict factual mode — we don't want hallucinations on a grounding call.
        temperature=0.0,
    )
    try:
        response = await client.aio.models.generate_content(
            model=chosen_model,
            contents=[text_turn("user", query)],
            config=config,
        )
    except Exception as e:
        return {
            "finding": "",
            "sources": [],
            "raw_queries": [],
            "ok": False,
            "error": str(e)[:300],
        }

    # Truncation detection — same architectural pattern as the sub-agent
    # output path. If Gemini hit MAX_TOKENS mid-stream, the response is
    # incomplete (tables cut off mid-row, sections ending in "3. The "...).
    # Surface this as a clean signal instead of returning the partial
    # text as if it were a complete answer — the chat would otherwise
    # render the half-table verbatim and confuse the founder.
    if was_max_tokens_truncated(response):
        return {
            "finding": "",
            "sources": [],
            "raw_queries": [],
            "ok": False,
            "error": (
                "Grounded search hit the output-token cap mid-response — the "
                "answer was cut off. Try a narrower claim (one specific fact "
                "at a time), or fall back to dispatching the relevant sub-agent."
            ),
        }

    text = extract_text(response).strip()
    candidate = response.candidates[0] if response.candidates else None
    grounding = getattr(candidate, "grounding_metadata", None) if candidate else None

    sources: list[dict] = []
    raw_queries: list[str] = []
    if grounding:
        # Web sources land under grounding_chunks; each has .web with uri + title.
        chunks = getattr(grounding, "grounding_chunks", None) or []
        seen_uris: set[str] = set()
        for ch in chunks:
            web = getattr(ch, "web", None)
            if not web:
                continue
            uri = getattr(web, "uri", "") or ""
            title = getattr(web, "title", "") or uri
            if not uri or uri in seen_uris:
                continue
            seen_uris.add(uri)
            sources.append({"label": title, "url": uri})
        queries_obj = getattr(grounding, "web_search_queries", None) or []
        raw_queries = [q for q in queries_obj if isinstance(q, str)]

    return {
        "finding": text,
        "sources": sources,
        "raw_queries": raw_queries,
        "ok": bool(text),
    }


# ─── Streaming with live thought surfacing ─────────────────────────────────

async def call_stream(
    model: str,
    system: str,
    contents: list[gtypes.Content],
    tool_declarations: list[gtypes.FunctionDeclaration] | None = None,
    thinking_budget: int | None = None,
    thinking_level: str | None = None,
    max_output_tokens: int = 65535,
):
    """Streaming variant that yields events as Gemini produces them.

    Yields one of:
        {"kind": "thought", "delta": str}   — incremental reasoning token(s)
        {"kind": "text",    "delta": str}   — incremental answer token(s)
        {"kind": "fc",      "part": Part}   — a function_call part (collect across chunks)
        {"kind": "final",   "candidate_content": Content, "fc_parts": [Part]}
                                            — after the stream ends; gives the
                                              assembled model-turn Content so
                                              callers can append it before
                                              sending function_responses

    No retry on streams (Vertex doesn't re-emit on transient errors mid-stream).
    For non-streaming callers, keep using `call()`.
    """
    client = get_client()
    config = _build_config(
        system, tool_declarations, thinking_level, thinking_budget,
        max_output_tokens, include_thoughts=True,
    )

    fc_parts: list[Any] = []
    text_chunks: list[str] = []
    thought_chunks: list[str] = []
    final_candidate_content: Any = None

    async for chunk in await client.aio.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config,
    ):
        cand = chunk.candidates[0] if chunk.candidates else None
        if not cand or not cand.content:
            continue
        final_candidate_content = cand.content
        for p in cand.content.parts or []:
            if getattr(p, "thought", False) and p.text:
                thought_chunks.append(p.text)
                yield {"kind": "thought", "delta": p.text}
            elif p.function_call is not None:
                fc_parts.append(p)
                # function_calls don't have meaningful partials — wait for final
            elif p.text:
                text_chunks.append(p.text)
                yield {"kind": "text", "delta": p.text}

    # Build a synthetic Content that mirrors what `call()` would have returned
    # — useful for the caller to append before any function_response turns.
    yield {
        "kind": "final",
        "candidate_content": final_candidate_content,
        "fc_parts": fc_parts,
        "text": "".join(text_chunks),
        "thoughts": "".join(thought_chunks),
    }
