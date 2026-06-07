"""The structured contract every specialist returns.

A specialist is stateless: Maya invokes it via the `task` tool, it runs to
completion in isolated context, and returns ONE structured result. With this set
as a subagent's `response_format`, the harness JSON-serializes it into the
ToolMessage Maya receives — so Maya always gets a validated object, never raw
(possibly empty) text.

Two branches:
  - status='complete'    -> the specialist did the work; `summary` + `detail` hold it.
  - status='needs_input' -> the specialist cannot proceed without a product
                            decision; `questions` lists what it needs. Maya
                            decides whether to answer from context or ask the
                            founder, then re-invokes.

Fields are deliberately primitives + lists of strings so Gemini structured
output is reliable. Specialist-specific payload shapes (Nora's PRD sections,
Hugo's ranked risks) are layered on per specialist later; for now the full body
travels in `detail` as markdown.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SpecialistResult(BaseModel):
    """The single report a specialist returns to Maya."""

    status: Literal["complete", "needs_input"] = Field(
        description=(
            "'complete' when you did the work. 'needs_input' ONLY when answering "
            "blind would produce a clearly wrong result and you need a product "
            "decision to proceed. Default to 'complete' with an honest caveat."
        )
    )
    summary: str = Field(
        description=(
            "One plain-language sentence: your headline finding or what you "
            "produced. Always fill this, in both branches. No jargon."
        )
    )
    detail: str = Field(
        default="",
        description=(
            "The full body of your work as markdown — evidence bullets, the "
            "drafted artifact, the ranked list, etc. Empty only when "
            "status='needs_input'."
        ),
    )
    questions: list[str] = Field(
        default_factory=list,
        description=(
            "When status='needs_input': the specific question(s) you need "
            "answered to proceed. Empty when status='complete'."
        ),
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "Source URLs backing any web research. Never invent sources; leave "
            "empty if you have none."
        ),
    )
