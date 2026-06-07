"""Maya's coordinator tools.

Phase 1 ships the steering primitive only: `ask_founder`. Domain tools (artifact
CRUD, decisions, dependency links, sprint) land in Phase 3.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_founder(question: str, options: list[str] | None = None) -> str:
    """Ask the founder a product question and wait for their answer.

    Use this ONLY when a decision genuinely needs the founder's judgment —
    something you cannot resolve from the PRD, prior decisions, guardrails, or
    context. Execution pauses until the founder responds; their answer is
    returned to you so you can continue in the same run.

    Args:
        question: The question to put to the founder, in plain language.
        options: Optional suggested choices to offer the founder.
    """
    payload: dict[str, Any] = {
        "kind": "ask_founder",
        "question": question,
        "options": options or [],
    }
    # Suspends the graph. When resumed via Command(resume=<value>), `interrupt`
    # returns that value. We accept either a bare string or a {"answer": ...} dict.
    answer = interrupt(payload)
    if isinstance(answer, dict):
        return str(answer.get("answer") or answer.get("value") or answer)
    return str(answer)
