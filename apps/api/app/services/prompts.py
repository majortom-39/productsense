"""Prompt loader. Reads markdown files from packages/prompts/ at startup."""
from __future__ import annotations

import os
from pathlib import Path


def _resolve_prompts_dir() -> Path:
    """Locate packages/prompts robustly across layouts.

    1. `PROMPTS_DIR` env var (set in the container image).
    2. Walk up from this file looking for a `packages/prompts` dir (the monorepo
       dev layout — services/ → app/ → api/ → apps/ → repo root).
    3. Safe fallback (never raises here; `load()` surfaces a clear error if a
       prompt file is actually missing).
    """
    env = os.getenv("PROMPTS_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "prompts"
        if candidate.is_dir():
            return candidate
    return here.parent / "packages" / "prompts"


_PROMPTS_DIR = _resolve_prompts_dir()


def load(name: str) -> str:
    """Return the contents of packages/prompts/<name>.md."""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


# Eager-load the canonical set so failures show at boot, not at first call.
MAYA = load("maya")
_DIALOG_RULES = load("_dialog_rules")
CONTRACT = load("_contract")

# Sub-agent prompts get the shared dialog rules appended — single source of
# truth for "how to interact with Maya in a clarification round-trip."
def _with_dialog(name: str) -> str:
    return load(name) + "\n\n---\n\n" + _DIALOG_RULES

IRIS = _with_dialog("iris")
AIDEN = _with_dialog("aiden")
HUGO = _with_dialog("hugo")
ZARA = _with_dialog("zara")
THEO = _with_dialog("theo")
NORA = _with_dialog("nora")
KAI = _with_dialog("kai")
