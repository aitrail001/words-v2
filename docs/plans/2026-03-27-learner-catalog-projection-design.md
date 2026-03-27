# Learner Catalog Projection Design

## Problem

The production-like benchmark on March 27, 2026 showed that the dominant database cost is the repeated `knowledge_catalog_projection` query family. The backend is still rebuilding the same learner catalog shape in request SQL for range loads, adjacency, list/search, and overview-style reads. On the tested single-host budget of `4 vCPU / 16 GB RAM`, only `1` concurrent mixed-workload virtual user remained inside the strict `p95 < 500ms` target. By `5` virtual users, `p95` had already risen above `700ms`, and `pg_stat_statements` showed the repeated catalog CTE variants dominating both total execution time and mean execution time.

## Decision

Introduce a persisted learner catalog projection table and move the shared catalog computation out of request time.

The projection will store only shared lexicon facts. User-specific learner status and review state remain live and are joined at request time.

## Projection Scope

The new projection table should hold one row per learner-visible entry and include:

- `entry_type`
- `entry_id`
- `display_text`
- `normalized_form`
- `browse_rank`
- `bucket_start`
- `cefr_level`
- `primary_part_of_speech`
- `phrase_kind`
- `is_ranked`

This is intentionally a read model, not the source of truth for full word/phrase detail content.

## Data Ownership Boundary

### Shared, precomputed facts

These are the same for all users and safe to persist in a shared projection:

- learner-visible text
- normalized search text
- browse rank
- bucket assignment
- CEFR
- primary learner POS
- phrase kind

### Live, user-specific facts

These must remain dynamic and must not be cached into the shared projection:

- `learner_entry_statuses`
- review queue state
- per-user progress counts
- user preferences

Request handling should therefore become:

1. read projection rows
2. left join or overlay current-user learner status
3. hydrate full normalized detail rows only when detail content is needed

## Rebuild Contract

The projection must rebuild automatically when lexicon imports change the source catalog.

`tools/lexicon/import_db.py` should own the rebuild. The import flow should:

1. write normalized source tables first
2. rebuild the projection deterministically from current source rows
3. commit only after the projection matches the imported catalog

The rebuild should be full-table and deterministic for the first slice. Partial incremental maintenance can be considered later if needed.

## Query Changes

The following hot paths should stop rebuilding `knowledge_catalog_projection` in SQL and instead query the persisted projection table:

- learner range bucket loads
- previous/next adjacency by browse rank
- learner list
- learner search
- overview/dashboard catalog reads where only shared catalog facts are needed

The following paths remain source-table based:

- word detail meaning/example/translation hydration
n- phrase detail sense/example/localization hydration
- review state and learner status reads

## Import and Export Considerations

The importer must rebuild the projection as part of normal success semantics so the projection does not drift after a lexicon import.

The projection is not an export artifact and does not replace normalized source tables. It is an internal read-optimization structure.

## Testing Strategy

Coverage should prove:

- projection rows rebuild correctly from current source tables
- learner range/list/search/adjacency queries read from projection-backed SQL
- user-specific status is still joined live
- import updates the projection automatically
- benchmark evidence shows the prior dominant SQL family materially reduced or removed

## Acceptance Criteria

- no learner hot request rebuilds the large `knowledge_catalog_projection` CTE in SQL
- `import-db` rebuilds the projection automatically
- focused backend and lexicon tests pass
- the production-like benchmark is rerun on the same stack
- the updated capacity report and status board include new evidence
