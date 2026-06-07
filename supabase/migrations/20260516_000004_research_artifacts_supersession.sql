-- Research artifacts get explicit supersession, mirroring decisions.
--
-- Problem: Maya pins a Deepgram-vs-Speechmatics comparison from Hugo, then
-- later Theo produces a refined version and Maya pins THAT too. The
-- dashboard ends up with two cards saying overlapping things and the
-- founder doesn't know which to trust.
--
-- Fix: pin/create can take a `supersedes` artifact_id. The old card is
-- soft-stamped (we set deleted_at — same column already used for
-- soft-deletes — but record the superseder via metadata.superseded_by so
-- chat history can still link forwards). Listing filters deleted_at IS NULL.
--
-- We intentionally REUSE deleted_at rather than adding a separate
-- superseded_at column: from the dashboard's perspective superseded cards
-- behave identically to deleted ones (hidden). The metadata distinction
-- preserves audit info for chat replay and for "show history" UI later.

-- No schema change required. We document the convention here so future
-- readers know `metadata.superseded_by = <new_artifact_id>` is a real
-- contract — not just an arbitrary metadata key.

-- Optional sanity index: speeds up "find what superseded X" queries the
-- audit panel may use.
create index if not exists research_artifacts_superseded_by_idx
  on research_artifacts ((metadata->>'superseded_by'))
  where deleted_at is not null;
