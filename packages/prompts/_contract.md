# Sub-Agent Contract

Every sub-agent (research and reasoning) follows the same input/output shape. This file documents it. Each `<name>.md` adjacent to this file is the system prompt for one specific sub-agent.

## Input

```python
class AgentInput(BaseModel):
    query: str                    # what Maya is asking
    context: AgentContext         # what Maya already knows
    budget: AgentBudget           # hard caps to prevent runaway loops

class AgentContext(BaseModel):
    prd_summary: str | None       # current PRD compressed to a paragraph
    decisions_summary: str | None # last N decided decisions, summarized
    guardrails: list[str] | None  # one-liners from guardrails.md
    scope_hints: list[str]        # caller-provided focus areas

class AgentBudget(BaseModel):
    max_calls: int = 8            # Firecrawl calls (research agents only)
    max_tokens: int = 4000        # output cap
    max_turns: int = 3            # internal reasoning iterations
```

## Output

```python
class AgentOutput(BaseModel):
    status: Literal["complete", "clarification_needed", "budget_hit"]
    finding: str | None           # one-sentence answer
    bullets: list[str] | None     # evidence
    sources: list[Source] | None  # citations (research agents only)
    confidence: float             # 0–1
    clarifying_question: str | None
    tokens_used: int
    calls_made: int

class Source(BaseModel):
    label: str                    # human-readable, e.g. "Reddit: r/MealPrepSunday"
    url: str
```

## Behavior

- If the query is unambiguous, return `status="complete"` with `finding`, `bullets`, optional `sources`.
- If the query is ambiguous (e.g., scope unclear, multiple interpretations), return `status="clarification_needed"` with a `clarifying_question`. Do NOT guess.
- If you hit your budget before completing, return `status="budget_hit"` with whatever you have, plus a hint of what you'd dig into next.
- Always populate `tokens_used` and `calls_made` (telemetry).
- Cite sources for any factual claim from the web. No invented citations.
- Plain English in `finding` and `bullets`. No jargon. No internal terms.

## What sub-agents do NOT do

- They do not chat with the founder.
- They do not write to `prd.md`, `sprint.md`, `decisions.md`, or `guardrails.md` directly. They return findings; Maya/Nora/Wes apply them.
- They do not invoke other sub-agents (no recursion). Maya is the orchestrator.
- They do not maintain memory across invocations. Every call is fresh.

## Models

- All sub-agents run on **Gemini 3.1 Flash Lite (preview)**.
- Maya runs on **Gemini 3.1 Pro (preview)** with thinking-medium config.
