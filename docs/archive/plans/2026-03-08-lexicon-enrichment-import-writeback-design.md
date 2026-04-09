# Lexicon Enrichment Import Writeback Design

## Goal

Extend the offline lexicon pipeline so compiled enriched output can populate the first learner-facing enrichment tables in the local DB, not just `words` and `meanings`.

## Scope

This slice should make `compile-export` and `import-db` persist:

- `meaning_examples`
- `word_relations`
- `lexicon_enrichment_jobs`
- `lexicon_enrichment_runs`
- word-level phonetic provenance fields when data exists

It should continue to update the existing `words` and `meanings` tables.

## Non-goals

This slice does **not** yet add:

- public API endpoints for examples/relations/enrichment runs
- admin UI for enrichment review
- phrase tables or `meaning_phrases`
- richer meaning fields such as usage notes/grammar patterns on DB tables not yet modeled
- direct live enrichment from backend workers

## Source of truth and mapping

The source remains the offline lexicon pipeline:

1. `build-base`
2. `enrich`
3. `validate`
4. `compile-export`
5. `import-db`

`compile-export` must preserve enough enrichment metadata for `import-db` to reconstruct learner-facing persistence.

## Minimal compiled-schema evolution

Add only the metadata required for DB writeback:

Per compiled sense:
- `enrichment_id`
- `generation_run_id`
- `model_name`
- `prompt_version`
- `confidence`
- `generated_at`

Keep existing learner-facing fields already emitted:
- `definition`
- `examples`
- `synonyms`
- `antonyms`
- `collocations`
- `primary_domain`
- `secondary_domains`
- `register`
- `usage_note`
- `grammar_patterns`

Word-level fields can stay limited to what already exists unless phonetics are later added to enrichment output.

## DB writeback design

### Word / Meaning

Keep current upsert behavior for `words` and `meanings`.

### Enrichment job / run mapping

Use one `LexiconEnrichmentJob` per `(word, phase1)`.

For each imported compiled sense, create or update one `LexiconEnrichmentRun` under that job keyed by the sense source reference plus generation metadata in importer logic.

This is intentionally pragmatic:
- jobs remain word-scoped
- runs represent chosen imported sense enrichments
- no attempt is made yet to reconstruct every historical candidate generation

### Meaning examples

For each imported meaning:
- replace or upsert example rows from the compiled `examples`
- preserve deterministic ordering via `order_index`
- attach `enrichment_run_id`
- use importer-managed replace-by-scope semantics for this source

### Word relations

Import only the clean learner-facing relation types that map well today:
- `synonym`
- `antonym`
- `confusable`

Do **not** import collocations as `word_relations` in this slice because they are often multi-word expressions and fit better with future phrase modeling.

For now:
- set `meaning_id` to the imported meaning when the relation is sense-scoped
- populate `related_word`
- leave `related_word_id` null unless the related word already exists and can be resolved cheaply
- attach `enrichment_run_id`

## Idempotence / incremental import behavior

Repeated `import-db` runs should be stable.

For a given imported sense:
- update the existing `Meaning`
- replace only its imported `meaning_examples`
- replace only its imported `word_relations` for the supported relation types
- reuse the existing word-scoped enrichment job when present
- reuse or update the matching enrichment run when importer metadata identifies the same imported sense

## Validation strategy

Tests should cover:
- compiled export preserves new sense-level provenance fields
- importer creates examples, relations, job, and run rows for new data
- importer updates without duplicating examples/relations/jobs on repeat import
- importer still supports the existing minimal fake-model test path

## Success criteria

This slice is complete when:
1. compiled output carries enough enrichment provenance for import
2. `import-db` writes examples and supported relations into the new schema
3. `import-db` records word-scoped enrichment job/run provenance
4. repeated import is stable for the same compiled rows
5. tests and focused verification pass
