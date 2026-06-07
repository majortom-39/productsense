"""Prompt loader. Reads markdown files from packages/prompts/ at startup."""
from __future__ import annotations

from pathlib import Path

# services/ → app/ → api/ → apps/ → repo root
_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "packages" / "prompts"


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
WES = _with_dialog("wes")
