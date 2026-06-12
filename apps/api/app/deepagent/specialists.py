"""The eight specialists, as stateless Deep Agents subagents.

Each entry is a `SubAgent` spec Maya's `task` tool can delegate to. A specialist
runs once in isolated context and returns ONE `SpecialistResult` — enforced by
`response_format`, so Maya always receives a validated object, never raw text.

Model assignment is read live from `settings` (same source the rest of the app
uses), so it tracks the .env overrides 1:1. Three tiers by reasoning depth:

  deep + HIGH    — Theo, Kai          (architecture / sprint planning)
  mid  + MEDIUM  — Nora, Hugo         (canonical synthesis, pattern detection)
  fast + none    — Iris, Aiden, Zara  (web research / formulaic output)

Web-bound specialists (Iris, Aiden, Zara, Hugo, Theo) get the research tools.
Synthesis-only specialists (Nora, Kai) work from the context Maya passes.
(Guardrails are compiled by Maya herself — no specialist needed.)
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain.agents.structured_output import ToolStrategy

from app.config import settings
from app.deepagent.contracts import SpecialistResult
from app.deepagent.models import build_chat_model
from app.deepagent.research_tools import RESEARCH_TOOLS
from app.deepagent.specialist_prompts import build_specialist_prompt


@dataclass(frozen=True)
class _Tier:
    model: str
    thinking_level: str | None


# Read live from settings → honors .env overrides automatically.
_DEEP = _Tier(settings.deep_model, "HIGH")
_MID = _Tier(settings.mid_model, "MEDIUM")
_FAST = _Tier(settings.fast_model, None)

# name -> (tier, gets_web_tools, one-line action description for Maya).
_SPECS: dict[str, tuple[_Tier, bool, str]] = {
    "iris": (
        _FAST, True,
        "Problem Validator. Delegate to find real-world evidence that the "
        "founder's problem is real and worth solving.",
    ),
    "aiden": (
        _FAST, True,
        "Competitor Mapper. Delegate to map who else solves this and where the "
        "gaps and openings are.",
    ),
    "zara": (
        _FAST, True,
        "User Researcher. Delegate to understand who the users are and how they "
        "describe the problem in their own words.",
    ),
    "hugo": (
        _MID, True,
        "Risk Researcher. Delegate to surface the likely failure modes and risks "
        "for this kind of product, ranked.",
    ),
    "theo": (
        _DEEP, True,
        "Tech Advisor. Delegate for a build approach and the key technical "
        "trade-offs a coding agent will hit.",
    ),
    "nora": (
        _MID, False,
        "PRD Writer. Delegate to turn the gathered context into a concise, "
        "decision-ready product requirements draft.",
    ),
    "kai": (
        _DEEP, False,
        "Sprint Planner. Delegate to turn the PRD into an intent-level sprint "
        "board a coding agent can pick up.",
    ),
}


def _build_subagent(name: str) -> dict:
    tier, gets_web, description = _SPECS[name]
    spec: dict = {
        "name": name,
        "description": description,
        "system_prompt": build_specialist_prompt(name),
        "model": build_chat_model(tier.model, tier.thinking_level),
        # ToolStrategy (NOT the provider's native JSON mode): the result arrives
        # via a tool call, and handle_errors=True feeds any parse failure back
        # to the model to retry. With native mode, one empty/malformed response
        # raised straight through the task tool and killed Maya's whole turn —
        # the founder just saw her go silent.
        "response_format": ToolStrategy(SpecialistResult, handle_errors=True),
    }
    if gets_web:
        spec["tools"] = list(RESEARCH_TOOLS)
    return spec


def build_specialists() -> list[dict]:
    """All eight specialist SubAgent specs, ready for `create_deep_agent`."""
    return [_build_subagent(name) for name in _SPECS]
