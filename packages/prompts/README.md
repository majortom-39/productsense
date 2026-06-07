# Prompts

Version-controlled system prompts for Maya and her sub-agents.

Loaded at backend startup. To iterate on a prompt, edit the markdown file and re-run the backend (or hot-reload, when wired).

## Files

- `_contract.md` — uniform input/output contract every sub-agent follows
- `maya.md` — Maya's orchestrator prompt (Gemini 3.1 Pro)
- `iris.md` — Problem Validator
- `aiden.md` — Competitor Mapper
- `hugo.md` — Risk Researcher
- `zara.md` — User Researcher
- `theo.md` — Tech Advisor
- `nora.md` — PRD Writer
- `kai.md` — Sprint Planner
- `wes.md` — Guardrail Compiler

## Editing rules

- Plain English. Every prompt should be readable by a non-technical PM.
- No timeboxes anywhere ("you have 30 seconds").
- Sub-agents must NEVER chat with the founder. Their output goes to Maya.
- Maya must NEVER expose sub-agent names in chat with the founder.
- Right-sized: each prompt is concise. If it's longer than ~600 lines, the agent is probably trying to do too much.
