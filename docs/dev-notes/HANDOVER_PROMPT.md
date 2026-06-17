# Next-session kickoff prompt

Copy-paste this as the first message in the next Claude Code chat for this project.

---

I'm continuing work on **ProductSense** at `C:\Majortom\Proojects\ProductSense`. The previous session did a deep diagnostic of a real project run (debate analyzer, project_id `87f4b441-9c78-49e5-99f8-a468cafb33f8`) by pulling chat, PRDs, sprints, decisions, research artifacts and agent_runs straight from Supabase. The verdict: output is **not** yet usable for a coding agent reading via MCP, and Maya's pacing is off (jumps to UI sketch turn 2, drafts PRD too early, dispatches silently).

The full 11-phase fix plan — with symptoms, fixes per file, and acceptance criteria for each — is in `HANDOVER_FIXES.md` at the repo root. Read that file first.

**What I want you to do:**

1. Read `HANDOVER_FIXES.md` end-to-end.
2. Confirm the execution order (migrations → blocking bugs → prompt-only → polish) makes sense or propose a better one.
3. Answer the two open questions at the bottom of the handover (MCP contract shape change for multi-sprint; external readers of the §Guardrails block).
4. Then start with **Phase 1 (block duplicate sprint generation)** — it's the smallest blocking bug and gives us a quick win to validate the dev loop is healthy.

**Don't:**
- Don't validate any fix against the debate project's existing data — spin a fresh project. Its DB is the symptom we're fixing.
- Don't reintroduce "v1" language — we standardised on "MVP" last session.
- Don't add hardcoded debate-app examples to prompts — the "examples illustrate shape, not content" meta-rule is intentional.

**Server reminders:**
- Backend: `uvicorn` on `0.0.0.0:8000` (not 127.0.0.1 — Windows IPv6 issue).
- Frontend: Vite on `:5176`. CORS does NOT include 5173.
- If the backend behaves like stale code is loaded, `taskkill /F /IM python.exe` and restart — there's a `/health` endpoint with a `stale_research_helpers_loaded` probe that confirms it.

Start by reading `HANDOVER_FIXES.md` and confirming the plan before touching code.
