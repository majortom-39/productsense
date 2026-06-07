# Agents

| Agent | Role | Model | Tools |
|---|---|---|---|
| **Maya** | Orchestrator | Gemini 3.1 Pro thinking-medium | Invokes any sub-agent + pure functions |
| **Iris** | Problem Validator | Gemini 3.1 Flash Lite | Firecrawl |
| **Aiden** | Competitor Mapper | Gemini 3.1 Flash Lite | Firecrawl |
| **Hugo** | Risk Researcher | Gemini 3.1 Flash Lite | Firecrawl |
| **Zara** | User Researcher | Gemini 3.1 Flash Lite | Firecrawl |
| **Theo** | Tech Advisor | Gemini 3.1 Flash Lite | Firecrawl |
| **Nora** | PRD Writer | Gemini 3.1 Flash Lite | (project context only) |
| **Kai** | Sprint Planner | Gemini 3.1 Flash Lite | (project context only) |
| **Wes** | Guardrail Compiler | Gemini 3.1 Flash Lite | (project context only) |

## Sub-agent invariants

- Every sub-agent follows the contract in `packages/prompts/_contract.md`.
- Sub-agents NEVER chat with the founder.
- Sub-agents NEVER invoke other sub-agents (no recursion).
- Maya NEVER exposes sub-agent names in founder chat.
- Each sub-agent invocation has a hard budget (max calls, max tokens, max turns).

## Where prompts live

`packages/prompts/<agent>.md`. Version-controlled, hand-edited. Loaded at backend startup.

## Adding a new sub-agent

Tier 2 sub-agents (planned, not in v1):
- Real-User Signal Synthesizer — for shipped products
- Pricing & GTM Advisor — for pre-launch / shipped
- UX Pattern Researcher — for stuck-mid-build moments

To add: write a `<name>.md` prompt, add a module to `apps/api/app/agents/`, register the tool with Maya. The contract and invocation framework stay the same.
