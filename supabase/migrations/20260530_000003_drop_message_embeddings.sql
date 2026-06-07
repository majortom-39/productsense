-- Remove the dead semantic-search vector layer.
--
-- The old "summarize + semantic-search over past messages" retrieval layer is
-- gone. The Deep Agents coordinator keeps linear checkpointed history and never
-- searched these embeddings; in code we removed the embeddings service, the
-- per-message embedding write, and the search_project_messages consumer. This
-- drops the matching database objects.
--
-- Verified beforehand: `messages.embedding` is the ONLY column of type `vector`
-- in the database, and `search_project_messages` is the only RPC that used it.

-- 1. Drop the semantic-search RPC (it has a `vector` parameter, so it must go
--    before the extension). Resolved by exact signature via regprocedure.
do $$
declare
  fn_sig text;
begin
  select oid::regprocedure::text into fn_sig
  from pg_proc
  where proname = 'search_project_messages'
  limit 1;
  if fn_sig is not null then
    execute 'drop function ' || fn_sig;
  end if;
end $$;

-- 2. Drop the per-message embedding column (and any index on it).
alter table messages drop column if exists embedding;

-- 3. Drop the now-unused pgvector extension.
drop extension if exists vector;
