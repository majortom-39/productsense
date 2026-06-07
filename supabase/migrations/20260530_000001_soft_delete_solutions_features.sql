-- Soft-delete for solutions & features.
--
-- Maya can now archive/supersede solutions and features (workstream C). We
-- reuse the same `deleted_at` soft-delete pattern already used by
-- discovery_artifacts: archiving stamps deleted_at, and the listing helpers in
-- services/artifacts.py filter `deleted_at is null`. Nothing is ever hard
-- deleted — chat history and the dependency graph keep resolving.

alter table solutions add column if not exists deleted_at timestamptz;
alter table features  add column if not exists deleted_at timestamptz;

-- Listing reads are "live rows, ordered" — index the live subset.
create index if not exists solutions_project_live_idx
  on solutions (project_id, created_at desc)
  where deleted_at is null;

create index if not exists features_project_live_idx
  on features (project_id, created_at desc)
  where deleted_at is null;
