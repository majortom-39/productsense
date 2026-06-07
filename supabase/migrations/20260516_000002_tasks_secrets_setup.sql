-- tasks.secrets_setup — per-secret onboarding guidance.
--
-- Each entry shape (written by Kai):
--   {
--     name: "DEEPGRAM_API_KEY",
--     signup_url: "https://console.deepgram.com/signup",
--     free_tier_note: "Deepgram offers $200 free credits at signup …",
--     ask_phrase: "I need a Deepgram API key for real-time …"
--   }
--
-- The coding agent (Claude Code / Cursor) reads this via MCP get_task,
-- checks .env for each `name`, and for any missing one pastes
-- `ask_phrase` into the IDE chat to request the key from the founder.
-- Cheapest possible handoff — no extra infra needed.

alter table tasks
  add column if not exists secrets_setup jsonb not null default '[]'::jsonb;
