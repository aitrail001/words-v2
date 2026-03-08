# Lexicon Learner Schema Evolution Design

## Goal

Extend the local DB and admin inspection API so the richer learner-facing fields already produced by the lexicon pipeline can be stored and inspected after `import-db`.

## Why this is the next slice

The lexicon admin tool is now closed as a working local-DB pipeline:

1. `build-base`
2. optional review-prep flow
3. `enrich`
4. `validate --snapshot-dir`
5. `compile-export`
6. `validate --compiled-input`
7. `import-db`

The remaining gap is not the offline generation pipeline. The gap is that the local DB and inspection API still persist only a subset of the compiled learner-facing schema.

## Scope

This slice should add persistence and read projection for learner-facing fields that are already present in compiled lexicon output.

### In scope

#### Word-level
- `cefr_level`
- top-level `part_of_speech`
- `confusable_words`
- latest imported learner-facing `generated_at` timestamp
- continue keeping existing:
  - `frequency_rank`
  - `word_forms`
  - phonetic provenance

#### Meaning-level
- `wn_synset_id`
- `primary_domain`
- `secondary_domains`
- `register`
- `grammar_patterns`
- `usage_note`
- optional sense-level `generated_at`
- keep existing:
  - `definition`
  - `part_of_speech`
  - `example_sentence`
  - ordering/source fields

#### Example-level
- example `difficulty`

#### API
- extend `GET /api/words/{word_id}/enrichment` to return these new persisted learner-facing fields
- keep the existing `GET /api/words/{word_id}` contract intentionally smaller unless there is a strong reason to widen it

## Non-goals

This slice should **not** include:

- phrase/idiom tables or `meaning_phrases`
- frontend/admin UI implementation
- staged-review publish unification with importer semantics
- worker-driven live enrichment from backend jobs
- changes to the canonical offline ingestion path
- broad public API redesign beyond the existing enrichment inspection endpoint

## Data model recommendation

### `words`

Add:
- `cefr_level` as `String(10)`
- `learner_part_of_speech` as `JSON`
- `confusable_words` as `JSON`
- `learner_generated_at` as timezone-aware timestamp

Rationale:
- top-level POS is naturally multi-valued
- `confusable_words` is a small structured list and does not yet justify a dedicated table
- storing the latest learner-facing generation timestamp is useful for admin inspection and incremental imports

### `meanings`

Add:
- `wn_synset_id` as `String(255)` nullable
- `primary_domain` as `String(64)` nullable
- `secondary_domains` as `JSON` nullable
- `register_label` as `String(32)` nullable
- `grammar_patterns` as `JSON` nullable
- `usage_note` as `Text` nullable
- `learner_generated_at` as timezone-aware timestamp nullable

Rationale:
- these are sense-scoped properties and belong on `meanings`
- they are also the most valuable fields for future learner-facing review and debugging

### `meaning_examples`

Add:
- `difficulty` as `String(10)` nullable

Rationale:
- this preserves the example-level learner difficulty already present in compiled output
- example difficulty is better stored on the example row than duplicated on the meaning

## Import mapping

### Word-level importer behavior
- upsert `cefr_level`
- upsert top-level learner POS array
- upsert `confusable_words`
- set `learner_generated_at` from compiled row `generated_at`
- keep existing `frequency_rank`, `word_forms`, phonetic, and source fields

### Meaning-level importer behavior
- upsert all in-scope sense metadata from each compiled sense
- preserve source-scoped update semantics already used by `import-db`

### Example-level importer behavior
- continue replacing source-scoped imported examples
- additionally persist `difficulty` per example

## API projection design

Extend the enrichment inspection endpoint response models with:

### Word-level response additions
- `cefr_level`
- `part_of_speech`
- `word_forms`
- `confusable_words`
- `learner_generated_at`

### Meaning-level response additions
- `wn_synset_id`
- `primary_domain`
- `secondary_domains`
- `register`
- `grammar_patterns`
- `usage_note`
- `learner_generated_at`

### Example-level response additions
- `difficulty`

This endpoint remains the admin/operator inspection surface and is the safest place to expose richer fields first.

## Migration strategy

1. Add a single migration for the new learner-facing columns.
2. Keep all new columns nullable for backward compatibility.
3. Do not backfill historic rows in this slice.
4. Let future imports progressively populate the new fields.

## Validation and compatibility

Tests should prove:
- migrations create the new columns successfully
- importer persists the new fields from compiled rows
- repeated imports remain stable
- enrichment inspection API returns the new data
- old rows without the new fields still read successfully

## Success criteria

This slice is complete when:
1. the local DB can persist the richer learner-facing fields already present in compiled JSON
2. `import-db` writes those fields without breaking current import behavior
3. `GET /api/words/{word_id}/enrichment` exposes the richer persisted data
4. focused tests cover migration/model/import/API behavior
5. CI remains green without expanding scope into phrases/admin UI
