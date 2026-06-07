# ProductSense — Session handoff (2026-05-26)

> **Read this file at the start of the next chat session to resume cleanly.**
> The big `HANDOFF.md` in this directory has the long-form architecture context. This file is the **session diff** — what changed today, where to find it, how to verify, what to do next.

---

## TL;DR — what's live right now

**32 fixes shipped in this session across 3 rounds.** All 37 end-to-end checks passing. Stack is production-shaped:

- **Backend** (`uvicorn :8000`) — fresh build with timing instrumentation + Vertex pre-warm + tighter sub-agent budgets + cache-optimized prompt layout
- **Frontend** (`vite :5176`) — Discovery tab redesigned (oldest-first feed, ReactMarkdown bodies), EventSource auto-reconnect, React.memo on chat messages, typing-lag fix
- **Maya model**: `gemini-3.5-flash` with dynamic thinking (was 3.1-pro-preview — ~10-14× cheaper)
- **Approval gate**: REMOVED entirely (was an anti-product mechanic) — Maya now trusts founder's natural language
- **Cache**: System prompt now in its own SystemMessage so Gemini implicit caching actually hits across turns
- **Per-project cost target**: $1.50-1.90 (was $3)

---

## 1. Critical file map (where every change landed)

### Backend — modified this session

| File | What changed |
|---|---|
| `apps/api/main.py` | FastAPI lifespan now pre-warms Vertex client on boot (best-effort, non-blocking) |
| `apps/api/app/services/checkpointer.py` | Postgres pool resilience (`min_size=0`, `max_idle=30s`, `check=check_connection`). Reset `_initialized` in close so re-init works after restart. |
| `apps/api/app/services/maya.py` | Session auto-recovery on `/maya/message` after restart. Phase-level timing instrumentation. Chip suppression for non-terminal events (only Locked/Pinned/Logged show). Junk-response fallback (no more `_ ` ghost messages). |
| `apps/api/app/services/maya_graph.py` | **SystemMessage SPLIT** — static system prompt separated from dynamic state block (caching fix). Compression DISABLED (was cache-bust source). Long-conversation reminder block injected when project > 25 messages. Founder memory recall in state block. |
| `apps/api/app/services/maya_tools_lc.py` | Approval gate `_gate()` is now a NO-OP. `_normalise_stories` helper added for Pydantic shape. `_record_dev_environment` answers Pydantic coercion. `_confirm_response.finding` returns `"Locked."` (was leaking stage-machine text). `draft_user_stories` + `remember_about_founder` tools added. |
| `apps/api/app/services/approval_gate.py` | `verify_founder_quote` no longer enforces anywhere (kept callable for back-compat). Word-boundary affirmative tokens supported. |
| `apps/api/app/services/agent_runner.py` | Per-agent budgets tightened (`max_calls=3`, `max_turns=2-3`). First-pass empty-candidates retry. Sub-agent memory writes via `subagent_memory.remember_finding`. `_emit_progress` for `agent_progress` SSE events. |
| `apps/api/app/services/discovery_state.py` | `save_draft` / `get_draft` helpers for stage drafts (used by draft → lock pattern). |
| `apps/api/app/services/founder_memory.py` | **NEW** — Phase 8 cross-project founder memory via LangGraph Store, privacy-gated. |
| `apps/api/app/services/subagent_memory.py` | **NEW** — per-(project, agent) memory namespace via Store. Recall block injected into sub-agent system prompts. |
| `apps/api/app/routes/maya.py` | `_get_or_create_session` (auto-recreate on missing). `/maya/abort` idempotent. |
| `apps/api/app/config.py` | LangSmith + Supabase DB URL settings, env-var forwarder for tracing. |
| `.env` | LANGSMITH_TRACING/API_KEY/PROJECT + SUPABASE_DB_URL. **⚠️ Both keys were shared in chat — rotate before production.** |

### Frontend — modified this session

| File | What changed |
|---|---|
| `apps/web/src/hooks/useMayaSession.ts` | EventSource auto-reconnect with exponential backoff. Re-calls `/maya/start` on reconnect. |
| `apps/web/src/components/ChatPanel.tsx` | `Bubble` wrapped in `React.memo` (no per-keystroke markdown re-render). Textarea auto-grow moved to `useEffect + requestAnimationFrame`. |
| `apps/web/src/components/DiscoveryTab.tsx` | Complete redesign — oldest-first flat feed, no 12-stage accordion, empty state, LockedOutputCard vs ResearchCard tiers, ReactMarkdown for prose bodies. |

### Prompt — modified this session

| File | What changed |
|---|---|
| `packages/prompts/maya.md` | 7 new/rewritten sections: chat-vs-artifact formatting standards, per-stage artifact body templates, judgment-not-gate, don't-restate-card-content, late-stage sub-agent nudges, aggressive `search_old_chat` triggers, log_decision nudges. |

### Migrations applied this session

1. `enable_rls_on_langgraph_tables` — RLS on checkpoint_* + store + store_migrations tables
2. `user_settings_cross_project_memory` — new `user_settings` table for `remember_across_projects` flag

### Tests

| File | What it covers |
|---|---|
| `apps/api/tests/e2e_production_readiness.py` | **37 checks across 7 sections.** Run with `python -u -X utf8 -m tests.e2e_production_readiness`. Currently green. Use this as the regression gate before deploy. |
| `apps/api/tests/cost_compare.py` | Per-model pricing comparison harness. |

---

## 2. How to start a clean dev session

**Boot order matters on Windows due to the WatchFiles slow-stall issue.**

```bash
# 1) Kill any stale workers
cmd //c "taskkill /F /IM python.exe"
cmd //c "taskkill /F /IM node.exe"

# 2) Start backend (separate terminal, leave it running)
cd C:\Majortom\Proojects\ProductSense\apps\api
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 python -u -X utf8 -m uvicorn main:app \
  --host 0.0.0.0 --port 8000 --reload \
  --reload-dir . --reload-dir ../../packages/prompts

# 3) Start frontend (separate terminal)
cd C:\Majortom\Proojects\ProductSense\apps\web
pnpm dev
```

**Boot signals to watch for in the backend log:**
- `[checkpointer] AsyncPostgresSaver + AsyncPostgresStore ready (Supabase)` — healthy
- `[main] Vertex pre-warm complete` — pre-warm fired (first user turn will be faster)

**The frontend goes live at http://localhost:5176**.

---

## 3. LangSmith MCP — set up BEFORE the next chat for direct trace access

The next session is much more powerful if I can pull LangSmith traces directly. **Do this before pasting the starter prompt.**

### Step 1 — Verify the package exists

```bash
npm view langsmith-mcp-server
```

- If it returns version info → package exists, proceed to Step 2
- If you get `404 Not Found` → tell the next session and we'll find the right package name (could be `@langchain/langsmith-mcp` or similar; check langchain docs)

### Step 2 — Register the MCP server in Claude Code

**If you have a LangSmith Personal Access Token:**
```bash
claude mcp add langsmith \
  --env LANGSMITH_API_KEY=lsv2_pt_YOUR_KEY \
  -- npx -y langsmith-mcp-server
```

The `--env` flag injects the key into the subprocess so the MCP server can authenticate. **Don't share the key in chat again** — paste it once into this command, then rotate.

### Step 3 — Restart Claude Code

Close the Claude Code window completely, then reopen. New MCP servers only load at session start.

### Step 4 — Verify in the next chat

In the next session, ask me: *"can you list tools from langsmith?"*. If wired correctly, I'll see `mcp__langsmith__*` tools and can query traces, projects, runs, etc.

### ✅ Current setup (verified working as of this session)

`~/.claude/mcp.json` has an entry `langsmith` using stdio transport via npx. The community TypeScript port (langchain-ai docs explicitly endorse this option). We confirmed the server starts: `LangSmith MCP server running on stdio`.

### Future upgrade path — OAuth Remote MCP (no API key)

The langchain-ai docs deprecate the hosted onrender.com URL and recommend the new OAuth-authenticated Remote MCP at `https://api.smith.langchain.com/mcp` (regional variants for EU/APAC/AWS). It uses OAuth 2.1 with dynamic client registration — no API key, no header config needed.

When you're ready to migrate (probably after Claude Code's MCP OAuth support is more mature):
```json
"langsmith": {
  "url": "https://api.smith.langchain.com/mcp",
  "type": "http"
}
```
Claude Code handles the OAuth dance on first use.

---

## 4. What to test in the UI BEFORE the next session

These are the highest-signal validation runs. **Refresh the browser first (Ctrl+Shift+R).**

| What to test | What to look for | Why it matters |
|---|---|---|
| Open existing project `030fa649...` | At top of Maya's first turn, watch for `⚠️ This project has N messages — you only see the most recent ~15...` reminder | Confirms SHIP-8 state-block reminder loaded |
| Ask Maya something that requires older context (*"do we still want the gentle voice?"*) | She should call `search_old_chat` before answering | Confirms SHIP-8 prompt nudges working |
| Start a fresh project, send "hi" | First-message latency should feel faster (10-20s vs prior 30-60s) | Confirms SHIP-4 pre-warm working |
| Send a turn with a tool call | Backend log should print `[MayaSession.timing] ... TURN_DONE: total=Nms` | Confirms SHIP-1 instrumentation working — paste the timing line if a turn feels slow |
| Mid-project, mention an architectural choice (*"let's use Supabase"*) | A `Decision logged` chip should fire | Confirms SHIP-6 + log_decision prompt nudge |
| Type a long message in chat input | Should be snappy regardless of message history length | Confirms SHIP-10 React.memo |
| Force-restart the backend mid-session | Frontend should auto-reconnect within ~5-10s, no manual refresh needed | Confirms SHIP-2 (frontend) auto-reconnect + SHIP-1 (backend) session re-create |
| Look at Discovery tab on existing project | Cards ordered oldest-first, no "SHOWING AS TEXT" warnings, **bold** labels render correctly on dev_environment + spec_recap cards | Confirms #8 redesign + ReactMarkdown bodies |
| Lock a stage | Chip should say `"Locked."` not `"Stage marked complete. Current stage: X"` | Confirms #3 chip text cleanup |
| Watch LangSmith dashboard for the next turn | `cached_content_token_count` should be > 0 starting turn 2 | Confirms cache-fix working |

If anything fails on this list, **paste the symptom + the relevant log lines** into the next chat — that's the highest-signal data for fast diagnosis.

---

## 5. Known follow-ups (deferred this session, real tickets)

| Ticket | Notes |
|---|---|
| Frontend Settings UI for `remember_across_projects` toggle | Backend done; UI is a separate ~30-min ticket |
| Frontend rendering of `agent_progress` events | Backend emits them; need a chip handler in `ChatPanel.tsx` |
| Frontend token-streaming during Maya's response | SSE supports `text_delta`; frontend currently waits for full message |
| Investigate cache-bust #3 (per-turn fragment churn) | Need LangSmith MCP next session to inspect actual request bytes in traces |
| Decide explicit Gemini context-caching API | 4-6 hour effort. Could drop cost another 40%. Worth it if usage grows. |
| Rotate `LANGSMITH_API_KEY` + `SUPABASE_DB_URL` password | Both were pasted in this chat. Production deploy must rotate. |

---

## 6. Starter prompt for the next chat

Paste this verbatim into the next session:

---

> I'm continuing ProductSense work at `C:\Majortom\Proojects\ProductSense`. Read `SESSION_HANDOFF.md` at the repo root for full context on what shipped in the previous session — there are 32 fixes deployed across 3 rounds, all 37 E2E checks passing, Maya on gemini-3.5-flash, approval gate removed, Discovery tab redesigned, session auto-recovery + frontend SSE reconnect both live.
>
> Before we start: please verify you can access the LangSmith MCP tools (`mcp__langsmith__*`). If yes, the very first thing I want you to do is pull the most recent 5 Maya turns from the `productsense` project and tell me the average per-turn cost + cached_content_token_count. This will validate whether the cache-fix from last session is actually firing in production.
>
> If you don't see the LangSmith MCP tools, tell me — I may have set it up wrong and we'll fix that first before continuing.
>
> Then: my open items I want to work through (in priority order):
> 1. [ANYTHING THAT BROKE in your manual testing — paste the symptom + log line]
> 2. Wire the frontend `agent_progress` chip handler (backend emits, no UI yet)
> 3. Add the Settings UI for cross-project `remember_across_projects` toggle
> 4. Audit one real LangSmith trace to find any remaining cost optimizations
>
> Don't start coding until I confirm. Start by reading SESSION_HANDOFF.md and verifying LangSmith MCP access.

---

## 7. Quick command reference

```bash
# Run the E2E regression test before any deploy
cd apps/api
python -u -X utf8 -m tests.e2e_production_readiness

# Compare model cost (existing harness)
python -u -X utf8 -m tests.cost_compare LABEL

# Health probe
curl -s http://127.0.0.1:8000/health

# Tail backend log
tail -f /tmp/api.log

# Check session timing (after a slow turn)
grep "MayaSession.timing" /tmp/api.log
```

---

*Session ended with backend live, frontend live, E2E green. The chat in your existing project is at message ~117. Refresh + continue, or start a fresh project to see the new behavior cleanly.*
