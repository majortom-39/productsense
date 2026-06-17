# Brainstorm Notes — open work from the agentic-design discussions

> Living doc. Captures decisions and pending work that came out of brainstorm sessions
> with the founder. Not a roadmap — a parking lot for ideas before they get scheduled.

## Conversational Maya (locked direction, not yet built)

**Decision:** Maya should converse and propose, not present menus. Sub-agent calls should
be mini-dialogues, not single shots.

### Pending work

1. **Honor `clarification_needed` round-trip end-to-end.**
   - Sub-agent contract already supports `status: "clarification_needed"` with a
     `clarifying_question` field (see `packages/prompts/_contract.md`).
   - Today the runner parses it but Maya's tool dispatch ignores it — just shoves the
     finding into the function_response and moves on.
   - Wire: when status=clarification_needed, surface the question to Maya as the
     function_response so she can answer-and-re-call, or push back.
   - Cap: max 2 clarification rounds per sub-agent invocation.

2. **Rewrite Maya's prompt for conversational mode.**
   - Drop the "force A/B/C with consequence" rule (or scope it to genuine forks the
     founder owns: target user, scope, fundamental product policy).
   - Add: "Lead with what you'd do, then check — 'sound right, or do you want me to
     dig in?' Use A/B framing only when there's a real fork."
   - Add: "You're a senior PM. You have opinions. Default to having them. Delegate
     when the answer is non-obvious or you'd be guessing."
   - Add explicit anti-examples (today she says things like "I just had Nora update
     the PRD" — leaks the abstraction; needs to die).

3. **"Thinking out loud" idiom before dispatch.**
   - Today Maya invokes silently — the agent card pops up cold. Add: "Before invoking
     a sub-agent that will take >5s, emit a 1-line thought naming what you're worried
     about." e.g. *"Hmm, diarization on noisy mic input is the part I'm worried about.
     Let me check what the actual ceiling is."*

4. **Sub-agent prompts: invite pushback.**
   - "You can ask Maya for clarification. Maya can also re-call you with 'are you
     sure?' or 'what about X edge case?' — handle gracefully and refine."

5. **Surface multi-turn dialog in the chat UI.**
   - Expandable card today shows brief → finding. Multi-turn means showing
     brief → clarifying-Q → answer → finding as a thread.
   - Visually: feel like watching Maya consult someone, not a structured form.

### Telemetry & cost gaps surfaced during the discussion

- `agent_runs.agent` is logging the inner tool name (`web_search`, `reddit_research`)
  instead of the sub-agent name (`theo`, `iris`, etc.). Lose the ability to say
  "Theo ran 3 times in this session." Easy fix in agent_runner.
- Nora / Kai / Wes don't appear in `agent_runs` at all (they call `gemini.call`
  directly, not through `run_agent`). Need a separate write path or a refactor.
- No memoization across sub-agent calls. Theo ran 3 times in one session with
  overlapping briefs. Either query-similarity cache at the runner level, or
  Maya remembers in her prompt context.

### UX bugs found in the same session

- "Maya is thinking…" sticks on after history loads. **Fixed.**
- Maya leaks sub-agent names in prose ("I just had Nora…"). Prompt rule violated.
- PRD got rewritten 5 times in one session — full-doc replace each time. Churn.
- Iris hit budget on problem validation; Maya never noticed, never retried.

