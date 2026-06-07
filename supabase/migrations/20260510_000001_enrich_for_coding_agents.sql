-- Enrich projects / sprints / tasks so a coding agent can pick up work
-- with the macro context, the locked tech decisions, and concrete
-- verification + pitfall guidance — not just a thin task description.
--
-- Driving principle: the agent should never have to re-derive a decision
-- the founder already made in chat. Move that signal into the artifact.

-- ─── project: macro / "what & why" ─────────────────────────────────────
alter table projects
  add column if not exists project_brief text,
  add column if not exists north_star    text;
-- project_brief: 1-2 paragraph elevator pitch the agent reads at every session start.
--                Includes who it's for, what it does, the differentiator/philosophy.
-- north_star:    single sentence "if you forget everything else, remember this."

-- ─── sprint: project-level context the agent needs once per sprint ─────
alter table sprints
  add column if not exists tech_stack    jsonb not null default '{}',
  add column if not exists data_models   jsonb not null default '[]',
  add column if not exists repo_layout   text,
  add column if not exists conventions   jsonb not null default '{}',
  add column if not exists existing_files jsonb not null default '[]';
-- tech_stack:     {framework, language, key_libs[], services[], models{}, ...}
-- data_models:    canonical shared type defs [{name, shape, notes}]
-- repo_layout:    markdown, where files go
-- conventions:    {styling, components, testing, error_handling, ...}
-- existing_files: snapshot at sprint start (auto-populated by sync CLI later)

-- ─── task: the per-task gaps the agent currently has to invent ─────────
alter table tasks
  add column if not exists tech_decisions   jsonb not null default '{}',
  add column if not exists data_contracts   jsonb not null default '[]',
  add column if not exists verification     jsonb not null default '[]',
  add column if not exists pitfalls         jsonb not null default '[]',
  add column if not exists complexity       text,
  add column if not exists secrets_required jsonb not null default '[]',
  add column if not exists refs             jsonb not null default '[]',
  add column if not exists prompt_brief     text;
-- tech_decisions:    {model: 'llama-3.1-70b-versatile', audio_format: 'linear16 16kHz mono'}
-- data_contracts:    [{name, shape, lifecycle: 'creates'|'consumes'|'mutates'}]
-- verification:      ["1. start dev server", "2. click Listen", "3. say X", ...]
-- pitfalls:          ["Deepgram disconnects on >30s silence — keepalive needed"]
-- complexity:        'low' (~50 LoC) | 'medium' (~150) | 'high' (~400+)
-- secrets_required:  ["DEEPGRAM_API_KEY", "GROQ_API_KEY"]
-- refs:              [{label, url}]
-- prompt_brief:      starter direction for any LLM system prompt this task needs.
--                    NOT a full prompt — a brief the coding agent expands on.

-- complexity check
alter table tasks
  drop constraint if exists tasks_complexity_check;
alter table tasks
  add constraint tasks_complexity_check
  check (complexity is null or complexity in ('low','medium','high'));
