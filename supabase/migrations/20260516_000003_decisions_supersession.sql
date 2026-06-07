-- Decisions get explicit supersession instead of stacking contradictions.
--
-- Problem: when the founder pivots ("actually let's use Firecrawl, not
-- Tavily"), Maya was logging a fresh decision without invalidating the old
-- one. The decisions log filled with contradictions and the coding agent
-- reading via MCP couldn't tell which choice was canonical.
--
-- Fix: superseding decisions reference the prior row; the prior row gets
-- stamped superseded_at + superseded_by atomically. Active queries filter
-- on superseded_at IS NULL.

alter table decisions
  add column if not exists supersedes      uuid references decisions(id),
  add column if not exists superseded_at   timestamptz,
  add column if not exists superseded_by   uuid references decisions(id);

-- Active-decisions index: most queries (Maya context, MCP get_session_context,
-- dashboard) want active rows only.
create index if not exists decisions_project_active_idx
  on decisions (project_id)
  where superseded_at is null;
