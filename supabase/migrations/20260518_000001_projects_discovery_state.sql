-- Projects get a structural `discovery_state` field tracking which of the
-- 5 discovery-stack layers Maya has marked as covered (or the founder has
-- explicitly waived) for this project.
--
-- Why: the layers are documented in maya.md as the discovery scaffold but
-- live only in Maya's prose reasoning. Several test runs showed her
-- jumping to PRD-draft before the layers were truly covered. This column
-- + the matching mark_layer_covered tool + the invoke_nora gate make the
-- scaffold structurally visible and lightly enforced.
--
-- Shape:
--   {
--     "layers": {
--       "1": {"covered": true, "evidence_run_ids": ["..."], "marked_at": "iso8601", "rationale": "..."},
--       "2": {...}, ...
--     },
--     "waivers": [<layer_num>, ...]    // founder-blessed skips
--   }
--
-- Empty/missing layer entries = not covered. Layers are numbered 1..5
-- (problem reality / people / competitive / friction / tech feasibility).

alter table projects
  add column if not exists discovery_state jsonb not null default '{}'::jsonb;
