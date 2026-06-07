-- Dynamic artifacts: clean-break redesign of how sub-agent output and
-- dashboard cards are stored.
--
-- Two-table model:
--   1. agent_runs        — every sub-agent invocation. Source of truth for
--                          dedup ("did Aiden already run this query?") and
--                          telemetry (tokens, cost, duration). Holds the
--                          full structured output the chat replays from.
--
--   2. research_artifacts — Maya-curated dashboard cards. Either pinned
--                          (one sub-agent run promoted as-is) or synthesized
--                          (Maya combined multiple runs into a new card).
--                          Renders into the right-panel Research tab.
--
-- Why a clean break:
--   - Old `research` table conflated raw sub-agent output with user-facing
--     artifacts. Couldn't tell what was Maya's curation from what was a
--     scratch run.
--   - Old `agent_runs` was telemetry-only (input_summary text). The new
--     model needs the full structured payload so the chat can render the
--     sub-agent's actual finding (table / chart / cards) inline.
--   - No back-compat shims — single migration, codebase moves wholesale.

-- ─── Drop the old world ───────────────────────────────────────────────────

drop table if exists research cascade;
drop table if exists agent_runs cascade;

drop type if exists research_category_enum;
drop type if exists research_status_enum;

-- ─── New enums ────────────────────────────────────────────────────────────

create type agent_run_status_enum as enum (
  'running',
  'complete',
  'error',
  'clarification_needed'
);

-- Render shapes a sub-agent or Maya can choose from. UI dispatches on this.
-- Bad payloads degrade to a text card on the frontend; backend stays liberal.
create type render_kind_enum as enum (
  'text',           -- markdown body
  'table',          -- {columns: string[], rows: any[][]}
  'matrix',         -- {row_labels, col_labels, cells}
  'bar_chart',      -- {categories, series:[{name, values}]}
  'line_chart',     -- {x_label, y_label, series:[{name, points:[{x,y}]}]}
  'graph',          -- {nodes:[{id,label,group?}], edges:[{from,to,label?}]}
  'persona_cards',  -- {personas:[{name, role, traits[], quote?, pains[]}]}
  'stack_diagram'   -- {layers:[{name, items[]}]}
);

create type artifact_created_by_enum as enum (
  'maya_pinned',       -- Maya promoted a single sub-agent run as-is
  'maya_synthesized'   -- Maya combined ≥1 runs into a new card
);

-- ─── agent_runs (rebuilt) ─────────────────────────────────────────────────
-- Every sub-agent invocation. Maya reads `output_payload` as her tool
-- result. Chat replays sub-agent exchanges from this table.

create table agent_runs (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,

  agent_name      text not null,                         -- iris | aiden | hugo | zara | theo | nora | kai | wes
  invoked_by      text not null default 'maya',          -- maya | mcp | system

  query           text not null,                         -- the exact prompt sent to the sub-agent
  query_hash      text not null,                         -- sha256(agent_name || normalized(query)) — dedup key

  status          agent_run_status_enum not null default 'running',
  output_payload  jsonb,                                 -- {render_kind, payload, finding, sources, ...}
  error_text      text,

  message_id      uuid references messages(id) on delete set null,  -- chat message this run rendered into

  tokens_in       int,
  tokens_out      int,
  cost_usd        numeric(10, 6),
  duration_ms     int,

  started_at      timestamptz not null default now(),
  ended_at        timestamptz
);

-- Dedup lookup: "has Aiden already run this query for this project?"
-- Filter to fresh-enough rows in app code (e.g. last 24h) when reading.
create index agent_runs_dedup_idx
  on agent_runs (project_id, agent_name, query_hash, started_at desc);

-- Recent activity feed
create index agent_runs_project_recent_idx
  on agent_runs (project_id, started_at desc);

-- Joining runs back to a chat message (replay)
create index agent_runs_message_idx
  on agent_runs (message_id)
  where message_id is not null;

-- ─── research_artifacts ───────────────────────────────────────────────────
-- Maya-curated dashboard cards. The Research tab reads from here.

create table research_artifacts (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,

  title           text not null,
  summary         text,                                  -- one-line preview shown when card is collapsed

  render_kind     render_kind_enum not null default 'text',
  payload         jsonb not null default '{}'::jsonb,    -- shape depends on render_kind

  source_run_ids  uuid[] not null default '{}',          -- provenance: agent_runs that fed this card
  created_by      artifact_created_by_enum not null,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz                            -- soft delete (chat history may still reference)
);

-- Dashboard listing: live cards, newest first
create index research_artifacts_project_live_idx
  on research_artifacts (project_id, created_at desc)
  where deleted_at is null;

-- Provenance lookup: "which artifacts cite this run?"
create index research_artifacts_source_runs_idx
  on research_artifacts using gin (source_run_ids);

-- ─── Updated-at trigger reuses set_updated_at() from init ─────────────────

create trigger research_artifacts_updated_at
  before update on research_artifacts
  for each row execute function set_updated_at();

-- ─── RLS ──────────────────────────────────────────────────────────────────

alter table agent_runs enable row level security;

-- Read: any user with access to the project sees their runs (telemetry)
create policy "scope by project (read)"
  on agent_runs for select
  using (project_id in (select id from projects where user_id = auth.uid()));
-- Writes happen via service role from the FastAPI backend (bypasses RLS).

alter table research_artifacts enable row level security;

create policy "scope by project (read)"
  on research_artifacts for select
  using (project_id in (select id from projects where user_id = auth.uid()));

-- Founder-direct mutations are not allowed. All artifact lifecycle goes
-- through Maya (which writes via service role). This keeps the dashboard
-- as Maya-curated and prevents silent drift between chat and dashboard.
