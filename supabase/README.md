# Supabase

Schema lives in `migrations/`. Apply via Supabase CLI:

```bash
supabase db push
```

Or via the Supabase dashboard SQL editor for the initial setup.

## Migrations

- `20260504_0001_initial_schema.sql` — all 9 tables + enums + triggers
- `20260504_0002_rls_policies.sql` — Row-Level Security per table

## Schema reference

See `~/.claude/projects/C--Majortom-Proojects-ProductSense/memory/database_schema.md` for the full schema doc, table-by-table column descriptions, and rationale.
