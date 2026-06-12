"""System prompts for the specialists, assembled cleanly for Deep Agents.

Each specialist's persona + domain expertise still lives in
`packages/prompts/<name>.md` — that content is rich and worth keeping. What
changes here is the OUTPUT CONTRACT: the old prompts told specialists to return
`finding` / `bullets` / `clarification_needed`. Under Deep Agents a specialist
instead returns a structured `SpecialistResult` (its `response_format`), so we
append a contract block that maps the persona's instincts onto the new schema
and explicitly supersedes any output-format wording in the body.

We deliberately do NOT edit the eight persona files. The appended block is the
single source of truth for output shape; the schema itself (enforced by the
harness) is the real guarantee.
"""
from __future__ import annotations

from app.services.prompts import load

# Appended to every specialist. Supersedes any "finding/bullets/
# clarification_needed" wording in the persona body. Field names here match
# SpecialistResult exactly.
_OUTPUT_CONTRACT = """
---

## How you return your work (this supersedes any output-format rules above)

You are a stateless specialist. Maya invokes you, you run once in isolation, and
you return ONE structured result. You never talk to the founder directly — Maya
is the only coach. Your result has these fields:

- **status** — `complete` when you did the work. `needs_input` ONLY when
  answering blind would produce a clearly wrong result and you need a product
  decision to proceed. Default to `complete` with an honest caveat. Use
  `needs_input` sparingly: a missing constraint that would flip your
  recommendation, a genuinely multi-interpretation question, or a case where the
  framing hides the real decision. Don't use it for low-stakes ambiguity — make a
  call and explain.
- **summary** — one plain-language sentence: your headline finding or what you
  produced. Always fill this, in both branches. No jargon.
- **detail** — the full body of your work as markdown: evidence bullets, the
  drafted artifact, the ranked list. Fill this when `status` is `complete`.
  Leave empty when `status` is `needs_input`. This renders in a CHAT for a
  non-technical founder: use `###` headings at most, short sections, bullets.
  NEVER paste raw JSON, code blocks, or data dumps into `summary` or `detail`
  — describe structured findings in plain words instead.
- **questions** — when `status` is `needs_input`, the specific question(s) you
  need answered to proceed. Empty when `complete`.
- **sources** — source URLs backing any web research. Never invent sources;
  leave empty if you have none.

When Maya re-invokes you, she's answering the question you asked or pushing for
another angle. Refine your prior thinking — don't start from zero — and return
`complete` this round unless something genuinely new came up.

Project vocabulary: never say "v1". The first ship is always the **MVP**.
"""


def build_specialist_prompt(name: str) -> str:
    """Persona body for `<name>` + the structured-output contract block."""
    return load(name) + _OUTPUT_CONTRACT
