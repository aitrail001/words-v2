# Legacy Learner JSON Drop and Phrase Cold-Path Design

## Goal

Remove duplicate learner JSON columns from hot lexicon tables now that normalized storage is established, and keep `phrase_entries.compiled_payload` as cold provenance rather than hot-path runtime data.

## Scope

In scope:
- Drop duplicate legacy columns from `lexicon.words`, `lexicon.meanings`, and `lexicon.translations`
- Remove remaining runtime/admin/export/import dependence on those columns
- Narrow phrase hot-path reads so `compiled_payload` is not fetched on learner/admin detail paths unless explicitly needed
- Add/update migration, API, importer, export, and admin coverage

Out of scope:
- Removing `phrase_entries.compiled_payload` entirely
- Splitting phrase provenance into a separate archival table
- Reworking phrase export contract away from provenance payloads
- Replacing the learner catalog with a materialized projection

## Schema Direction

Drop these duplicate columns:
- `words.learner_part_of_speech`
- `words.confusable_words`
- `words.word_forms`
- `meanings.secondary_domains`
- `meanings.grammar_patterns`
- `translations.examples`

Keep these normalized tables as the only authoritative storage for the corresponding learner/admin/export data:
- `lexicon.word_part_of_speech`
- `lexicon.word_confusables`
- `lexicon.word_forms`
- `lexicon.meaning_metadata`
- `lexicon.translation_examples`

Keep `words.phonetics` unchanged because it is small, fixed-shape, and not part of the duplicated normalized-field problem.

## Runtime Direction

All active read paths must use normalized storage only:
- learner knowledge-map routes
- main words API
- lexicon inspector admin routes
- lexicon export tooling

Any remaining fallback logic to the dropped JSON columns must be removed in the same slice. If a path still needs those columns, the migration is not ready.

## Import/Export Direction

`tools/lexicon/import_db.py` writes only normalized storage for word POS, word confusables, word forms, meaning metadata, and translation examples.

`tools/lexicon/export_db.py` reads normalized collections for those same fields. Export remains contract-compatible at the JSONL boundary, but it must reconstruct that contract from normalized rows rather than legacy DB columns.

## Phrase `compiled_payload` Strategy

Keep `phrase_entries.compiled_payload` and `seed_metadata` for provenance/export compatibility, but treat them as cold data.

Rules:
- learner list/detail routes must not load the blob
- admin hot detail/list paths must not load the blob unless the route explicitly presents provenance/raw compiled content
- export/provenance flows may still use the blob when appropriate

This reduces row-width cost without taking on the larger archival-table migration in the same slice.

## Migration Strategy

Use a single new Alembic revision.

Migration behavior:
- assume prior normalization migrations already ran and populated normalized tables
- perform no new backfill in this revision
- drop the six duplicate columns from the live tables

Because there is no compatibility fallback after this revision, the code change and migration must ship together.

## Risks and Mitigations

### Hidden Readers/Writers

Risk:
- some admin/export/test path still reads or writes a dropped column

Mitigation:
- grep-driven audit before code removal
- failing tests for each path family
- focused verification on learner API, words API, inspector, export, and importer

### Phrase Provenance Drift

Risk:
- narrowing phrase detail queries accidentally removes data expected by a provenance-oriented path

Mitigation:
- only de-hot-path learner/admin runtime routes
- leave export/provenance code paths explicit about when they need `compiled_payload`

### Migration Safety

Risk:
- local/live DB upgrade fails because a hidden ORM path still references removed columns

Mitigation:
- targeted migration-aware verification on the rebuilt Docker stack after code changes

## Acceptance Criteria

- no runtime/admin/export/import path depends on the dropped columns
- duplicate-column writes are removed from the importer
- learner and admin word detail still expose the same contract through normalized rows
- export still emits the expected JSONL contract from normalized data
- learner smoke passes on the real Docker stack
- phrase learner/admin hot paths do not fetch `compiled_payload`
