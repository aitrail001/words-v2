# Lexicon Staging COPY Import Design

**Date:** 2026-03-28
**Scope:** Replace the remaining Python/ORM-bound `import-db` hot path with a Postgres-first staging import path built around `COPY` and set-based SQL merge.

## Goal

Reduce full-fixture import wall-clock materially below the current `164.70s` baseline while preserving exact import->export round-trip parity for the checked-in compiled fixtures.

## Current state

The importer has already been hardened and optimized in three layers:
- chunked commits instead of one giant transaction
- parent-side ORM cascade for the safe graph portions
- Core bulk insert for hot child tables (`MeaningExample`, `TranslationExample`, `WordRelation`)

That got the full fixture down from `458.14s` to `164.70s`.

The remaining bottleneck is architectural:
- Python still parses every row into object-heavy structures
- the importer still constructs parent ORM rows one by one
- merge/update semantics are implemented in Python loops rather than set-based SQL

## Recommended architecture

### Import modes

Keep two import modes:
- `orm` - existing importer, fallback path for tests/small data/debugging
- `staging` - new high-throughput path using Postgres staging tables and set-based merge

Initial rollout shape:
- add `--import-mode orm|staging`
- keep default on the current path until staging proves itself
- once stable, flip the default to `staging`

### Staging pipeline

1. Read compiled JSONL rows and stream them into a raw staging table.
2. Normalize raw staged payload into typed staging tables.
3. Merge top-level entries first.
4. Replace child tables with set-based delete/insert or upsert statements.
5. Rebuild learner catalog once at the end.

### Staging tables

Use dedicated staging tables under `lexicon` or `lexicon_stage` for the import job scope.

Required tables:
- `staging_compiled_rows`
- `staging_words`
- `staging_meanings`
- `staging_meaning_examples`
- `staging_translations`
- `staging_translation_examples`
- `staging_word_relations`
- `staging_phrases`
- `staging_phrase_senses`
- `staging_phrase_sense_localizations`
- `staging_phrase_examples`
- `staging_phrase_example_localizations`
- optional `staging_reference_entries`
- optional `staging_reference_localizations`

Each staging row must carry:
- `import_run_id`
- stable natural key fields
- normalized payload columns only

### Merge semantics

#### Words
- merge words by `(language, word)`
- update top-level learner fields from staged rows
- preserve current source/provenance semantics

#### Meanings
- key by current source-reference convention
- replace/update meanings sourced from the current import source

#### Meaning examples
- for meanings touched by the import, replace staged-source examples set-based

#### Translations
- merge by `(meaning_id, language)`

#### Translation examples
- for translations touched by the import, replace example rows set-based

#### Word relations
- for meanings touched by the import, replace supported relation types set-based

#### Phrases
- merge phrase entries by normalized form/language
- replace child phrase graph set-based within the import scope

### COPY mechanics

Use Postgres-native ingest rather than ORM row insertion.

Preferred shape:
- build chunk-local TSV/CSV payloads in memory or temp files
- use psycopg `copy_expert` or equivalent sync connection path
- keep chunk boundaries so progress reporting stays visible

### Correctness requirements

The staging path is only acceptable if it preserves:
- row identity parity at export level for the checked-in fixtures
- top-level key parity
- exact translation parity
- current allowed normalization only (`forms.verb_forms.*` empty-placeholder cleanup)

### Operational requirements

- chunked visibility/progress remains available
- failures should identify stage (`copy raw`, `normalize`, `merge words`, `merge children`, etc.)
- import runs should be isolated by `import_run_id`
- cleanup of staging rows should happen at end, with an option to retain for debugging

## Tradeoffs

### Benefits
- much lower Python overhead
- less ORM state tracking
- far better throughput ceiling for 30k+ imports
- SQL becomes explicit for merge semantics

### Costs
- more SQL complexity
- more migration/DDL work
- staging schema must be maintained alongside the compiled contract
- fallback/import-mode duality during rollout

## Recommendation

Implement the staging path in slices:
1. raw staging + staged words/meanings/examples/translations/relations for word rows
2. phrase staging and phrase merge
3. reference staging if needed
4. default flip after parity and benchmark evidence

## Acceptance criteria

- `import-db --import-mode staging` completes the full fixture faster than `164.70s`
- `export-db` output after staging import round-trips exactly against `tests/fixtures/lexicon-db/full/approved.jsonl`
- no translation parity drift
- fallback `orm` path remains working
