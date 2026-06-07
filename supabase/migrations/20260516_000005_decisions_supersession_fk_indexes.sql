-- Cover the two foreign keys introduced by 20260516_000003 so chain walks
-- (find prior decision, find successor decision) are indexed. Without
-- these, FK constraint validation and any "what supersedes X" / "what did
-- Y supersede" lookup is a sequential scan.
--
-- Partial indexes are sized to active rows only — most decisions never
-- supersede anything, so a full-table index would be mostly NULL.

create index if not exists decisions_supersedes_idx
  on decisions (supersedes)
  where supersedes is not null;

create index if not exists decisions_superseded_by_idx
  on decisions (superseded_by)
  where superseded_by is not null;
