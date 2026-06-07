-- research_artifacts gets a metadata jsonb column.
--
-- Used at pin/create time to store provenance + extras the dashboard
-- needs to display:
--   { source_agents: ["aiden", "hugo"] }   ← which sub-agents fed the card
--
-- Default '{}'::jsonb so existing rows backfill cleanly. Future ingestors
-- can write additional keys (e.g. confidence, sample_size).

alter table research_artifacts
  add column if not exists metadata jsonb not null default '{}'::jsonb;
