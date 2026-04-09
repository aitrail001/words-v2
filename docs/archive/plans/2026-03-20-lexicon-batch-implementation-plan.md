# Lexicon Batch Enrichment Implementation Plan

## Purpose

This plan is the execution blueprint Codex should follow to implement the batch-first lexicon enrichment tool safely inside the current `words-v2` repository.

This updated version expands scope to include a third lightweight dataset for learner-reference entries such as names, place names, titles, demonyms, and common abbreviations.

The plan is intentionally staged, test-first, and biased toward preserving the current CLI and artifact contracts.

---

## Operating principles

1. Do not break existing `tools/lexicon` CLI commands.
2. Do not remove synchronous enrich mode.
3. Prefer extraction and refactoring over rewriting.
4. Add fixtures before or together with new logic.
5. No stage is complete until its tests pass.
6. No live OpenAI calls in unit or scenario tests.
7. Preserve deterministic snapshot → compile → import boundaries.
8. Treat `reference` as a first-class entry family, but keep its schema intentionally lightweight.
9. Keep learner-priority domain terms like housing / health / work vocabulary inside the main word corpus, not the reference family.

---

## Directory targets

Expected new or modified paths:

```text
tools/lexicon/
  batch_prepare.py
  batch_client.py
  batch_ingest.py
  batch_ledger.py
  qc.py
  overrides.py
  phrase_pipeline.py
  reference_pipeline.py
  inventory.py
  contracts.py
  schemas/
    word_enrichment_schema.py
    phrase_enrichment_schema.py
    reference_entry_schema.py
    qc_verdict_schema.py
    compiled_export_schema.py
  docs/
    batch.md
tests/
  lexicon/
    fixtures/
      snapshots/
      batch_inputs/
      batch_outputs/
      compiled/
      reference_seeds/
    test_batch_prepare.py
    test_batch_ingest.py
    test_batch_ledger.py
    test_phrase_pipeline.py
    test_reference_pipeline.py
    test_qc.py
    test_overrides.py
    scenarios/
    e2e/
```

---

## Stage 0 — Repo-safe scaffolding and fixture base

### Objective
Create the foundation without changing behavior.

### Tasks

- Add `tools/lexicon/docs/batch.md` placeholder.
- Add new module skeletons with imports and docstrings only.
- Add fixture directories:
  - `tests/lexicon/fixtures/snapshots/`
  - `tests/lexicon/fixtures/batch_inputs/`
  - `tests/lexicon/fixtures/batch_outputs/`
  - `tests/lexicon/fixtures/compiled/`
  - `tests/lexicon/fixtures/reference_seeds/`
- Add helper builders for small fake snapshots.
- Add golden JSONL fixture loader utilities.
- Add repo skills:
  - `lexicon-batch-contracts`
  - `lexicon-schema-guardrails`
  - `lexicon-test-harness`
- Add minimal curated sample seed files for:
  - names
  - places
  - abbreviations

### Acceptance criteria

- No existing tests regress.
- New test package imports cleanly.
- New skill folders exist and are discoverable.
- No production behavior change yet.

### Tests

- `test_fixture_loading.py`
- `test_skill_paths_documented.py`
- `test_reference_seed_fixture_loading.py`

---

## Stage 1 — Extract contracts and validation boundaries

### Objective
Separate schemas and validators from monolithic enrichment flow.

### Tasks

- Extract shared constants from `enrich.py`:
  - CEFR enums
  - register enums
  - required locales
  - relation type enums
- Move response schema builders into `tools/lexicon/schemas/`.
- Create pure normalization functions that accept parsed dicts and return validated canonical dicts.
- Add max length and max item constraints for:
  - synonyms
  - antonyms
  - collocations
  - grammar patterns
  - examples
  - common mistakes
- Add phrase schema definitions.
- Add lightweight reference schema definition with:
  - `reference_type`
  - pronunciation fields
  - `brief_description`
  - localization `display_form`
  - localization `translation_mode`
  - localization `brief_description`

### Acceptance criteria

- Existing synchronous enrich path still passes.
- Word schema validation behavior is preserved or tightened intentionally.
- Phrase schemas can be loaded and validated offline.
- Reference schemas can be loaded and validated offline.

### Tests

- `test_word_schema_validation.py`
- `test_phrase_schema_validation.py`
- `test_reference_schema_validation.py`
- `test_normalization_preserves_existing_contract.py`

### Safety checks

- Do not change CLI output format yet.
- Do not change import-db behavior yet.

---

## Stage 2 — Batch ledger and request builder

### Objective
Create deterministic batch request generation without touching the network.

### Tasks

- Implement `batch_ledger.py`.
- Implement `batch_prepare.py`.
- Add `batch-prepare` CLI command.
- Build request selection rules:
  - skip already accepted entries
  - skip published entries unless forced
  - select by entry kind (`word`, `phrase`, `reference`)
  - select by explicit IDs or limit when requested
- Implement shard splitting:
  - max request count
  - max byte size
  - single model per shard
  - single prompt version per shard
- Implement `custom_id` generation and parsing for all entry kinds.
- Emit:
  - `batch_requests.jsonl`
  - `batch_jobs.jsonl` placeholder rows
  - `batches/batch_input.<shard>.jsonl`

### Acceptance criteria

- Batch request files are deterministic from the same snapshot.
- `custom_id` round-trips correctly.
- Already-completed entries are excluded unless explicitly forced.
- Word, phrase, and reference request builders all work.

### Tests

- `test_batch_prepare_deterministic.py`
- `test_custom_id_round_trip.py`
- `test_shard_size_limits.py`
- `test_skip_completed_entries.py`
- `test_phrase_batch_prepare.py`
- `test_reference_batch_prepare.py`

### Scenario tests

- same snapshot + same config → identical request files
- same snapshot + changed prompt version → identical selection, different `custom_id`s
- same reference seed snapshot + same config → identical request files

---

## Stage 3 — Mockable Batch API client and submit/status flow

### Objective
Add a thin API layer that is easy to test and easy to replace.

### Tasks

- Implement `batch_client.py` methods:
  - `upload_batch_file`
  - `create_batch`
  - `get_batch`
  - `download_file`
- Add `batch-submit` CLI.
- Add `batch-status` CLI.
- Record provider identifiers in `batch_jobs.jsonl`.
- Keep the client small and dependency-light.
- Inject transport or SDK wrapper for tests.

### Acceptance criteria

- Submit/status code paths work with a fake client.
- No live network required in tests.
- Batch metadata is recorded immediately and idempotently.

### Tests

- `test_batch_client_mocked.py`
- `test_batch_submit_cli.py`
- `test_batch_status_cli.py`

### Safety checks

- No ingestion yet.
- No compile or import changes.

---

## Stage 4 — Output ingestion, normalization, and failure handling

### Objective
Turn batch outputs into validated enrichment artifacts.

### Tasks

- Implement `batch-ingest`.
- Parse output file and error file.
- Resolve every output line by `custom_id`.
- Normalize and validate every accepted payload.
- Append accepted normalized payloads into `enrichments.jsonl`.
- Record rejected items in:
  - `enrich.failures.jsonl`
  - `batch_results.jsonl`
- Update checkpoint / completion state.

### Acceptance criteria

- Out-of-order output files ingest correctly.
- Invalid payloads are recorded but do not crash the whole ingestion run.
- Re-ingesting the same completed batch is idempotent.
- Reference-family invalid localizations are rejected cleanly.

### Tests

- `test_batch_ingest_scrambled_output.py`
- `test_batch_ingest_invalid_schema.py`
- `test_batch_ingest_error_file.py`
- `test_batch_ingest_idempotent.py`
- `test_reference_batch_ingest_invalid_localization.py`

### Scenario tests

- mixed valid + invalid + transport error lines
- duplicate output ingest run
- partial output file and missing entries
- mixed word / phrase / reference snapshots on the same repository run

---

## Stage 5 — Retry, repair, and escalation workflows

### Objective
Make failures operationally manageable.

### Tasks

- Implement `batch-retry`.
- Support retry sources:
  - schema failure
  - transport failure
  - QC reject
  - explicit review export
- Support retry modes:
  - `repair`
  - `regenerate`
  - `escalate-model`
- Add configurable escalation rules.
- Preserve previous attempts in ledgers; never overwrite them.

### Acceptance criteria

- A failed subset can produce a new shard without touching accepted rows.
- Attempts increment correctly.
- Escalated retries carry different model provenance.
- Reference-family retries preserve lightweight prompt/schema selection.

### Tests

- `test_batch_retry_from_failures.py`
- `test_batch_retry_escalation.py`
- `test_attempt_increment.py`
- `test_reference_retry_generation.py`

### Safety checks

- Never delete previous failure history.
- Never silently replace accepted rows.

---

## Stage 6 — Phrase / idiom / phrasal verb pipeline

### Objective
Support the 5k phrase corpus end-to-end.

### Tasks

- Add phrase seed loader(s):
  - CSV
  - JSONL
- Add phrase normalization rules.
- Add `phrase-build-base`.
- Add phrase enrichment prompts and schemas.
- Add phrase compile path.
- Extend import logic for phrase-related tables and localizations.

### Acceptance criteria

- Phrase snapshot creation works from seed files.
- Phrase batch prepare / ingest / compile works.
- Phrasal verbs and idioms have distinct typed fields.

### Tests

- `test_phrase_seed_loader.py`
- `test_phrase_normalization.py`
- `test_phrase_compile_export.py`
- `test_phrase_import_mapping.py`

### Scenario tests

- mixed phrase types in one seed file
- multi-meaning phrasal verb
- idiom with usage pragmatics

---

## Stage 6B — Lightweight learner reference entries

### Objective
Support names, place names, titles, demonyms, abbreviations, and other lightweight learner-reference items with a smaller enrichment contract.

### Tasks

- Add curated seed loader(s) for:
  - common given names
  - famous people
  - fictional characters
  - countries
  - cities
  - landmarks / regions
  - demonyms
  - language names
  - titles / honorifics
  - common abbreviations
  - address abbreviations
- Add `reference-build-base`.
- Add `reference_entry_schema.py`.
- Add `reference_pipeline.py`.
- Add compile/export support for `references.enriched.jsonl`.
- Add DB import mapping for `reference_entries` and `reference_localizations`.
- Support localization `translation_mode` values:
  - `unchanged`
  - `localized`
  - `transliterated`

### Acceptance criteria

- Reference seed snapshot creation works from CSV and JSONL.
- Reference batch prepare / ingest / compile works.
- Names and place names do not require the full word/phrase enrichment schema.
- Localized forms support unchanged / transliterated / localized display names.
- Reference-family QC uses the smaller contract correctly.

### Tests

- `test_reference_seed_loader.py`
- `test_reference_normalization.py`
- `test_reference_schema_validation.py`
- `test_reference_compile_export.py`
- `test_reference_import_mapping.py`

### Scenario tests

- common given name with pronunciation help
- fictional character with unchanged localized form
- country with localized exonym
- city with identical display form across locales
- abbreviation with explanation
- title / honorific with pronunciation and concise description

---

## Stage 7 — QC pass and review queue

### Objective
Reduce human review load to a small flagged subset.

### Tasks

- Implement deterministic heuristics:
  - duplicate examples
  - missing headword in example when required
  - invalid CEFR
  - suspiciously long or abstract definition
  - locale example count mismatch
  - reference description too long
  - invalid reference `translation_mode`
  - empty reference localized display form
- Implement optional LLM QC verdict pass.
- Add `batch-qc`.
- Emit `enrichment_review_queue.jsonl`.
- Add `manual_overrides.jsonl` schema and loader.

### Acceptance criteria

- QC produces stable machine-readable flags.
- Review queue generation is deterministic from the same inputs.
- Overrides can be loaded and validated.
- Word, phrase, and reference families can all produce flags.

### Tests

- `test_qc_heuristics.py`
- `test_qc_verdict_schema.py`
- `test_review_queue_generation.py`
- `test_manual_overrides_validation.py`
- `test_reference_qc_heuristics.py`

### Safety checks

- QC does not mutate accepted enrichment artifacts.
- Manual overrides are layered, not destructive.

---

## Stage 8 — Compile/export and DB schema alignment

### Objective
Make the richer enrichment payload publishable.

### Tasks

- Extend compiled export format for:
  - learner metadata
  - example metadata
  - localizations
  - phrase enrichments
  - reference entries
- Add DB migration plan and implementation for:
  - word pronunciation split (`ipa_us`, `ipa_uk`)
  - localization tables
  - meaning / phrase learner metadata
  - example metadata
  - `reference_entries`
  - `reference_localizations`
- Update `import-db` to load the richer compiled output.
- Preserve existing import summary behavior.

### Acceptance criteria

- `compile-export` produces valid publishable JSONL for words, phrases, and references.
- `validate --compiled-input` validates the richer rows.
- `import-db --dry-run` shows correct counts for new entities.
- Existing words-only compiled rows still import if backward-compatible mode is enabled.

### Tests

- `test_compile_export_rich_rows.py`
- `test_compiled_validation.py`
- `test_import_db_dry_run_rich_rows.py`
- `test_backward_compat_compiled_rows.py`
- `test_reference_compiled_rows.py`

### Safety checks

- DB writes remain behind `import-db`.
- No enrichment step writes directly into SQL.

---

## Stage 9 — Operator docs, reporting, and end-to-end harness

### Objective
Finish the pipeline as an operator-ready system.

### Tasks

- Write `tools/lexicon/docs/batch.md`.
- Add reporting utilities and CLI summaries.
- Add small end-to-end harness that runs entirely from fixtures and mocks.
- Document the recommended production runbook:
  - build-base
  - phrase-build-base
  - reference-build-base
  - batch-prepare
  - batch-submit
  - batch-ingest
  - batch-qc
  - review-apply
  - compile-export
  - validate
  - import-db
- Add cost-estimate reporting by model.
- Document recommended curated seed-pack strategy for learner-priority domains.

### Acceptance criteria

- Operator docs are complete and accurate.
- A mocked full pipeline e2e test passes.
- Reviewer can inspect one flagged entry end-to-end with override application.
- Operator docs mention reference seeds and learner-priority seed packs.

### Tests

- `e2e/test_words_batch_round_trip.py`
- `e2e/test_phrase_batch_round_trip.py`
- `e2e/test_reference_batch_round_trip.py`
- `e2e/test_flagged_entry_override_round_trip.py`

---

## Test matrix

### Unit tests

Pure logic, no filesystem/network side effects beyond temp dirs.

Focus:

- schema validation
- request building
- `custom_id`
- ledgers
- normalization
- override merging

### Scenario tests

Filesystem-heavy, but fully offline.

Focus:

- multi-shard snapshots
- resume after partial ingestion
- out-of-order outputs
- mixed error classes
- reference seed pipelines

### End-to-end tests

Small mocked workflow from snapshot to compiled output.

Focus:

- whole pipeline wiring
- CLI integration
- backward compatibility with existing commands
- three-family compile/export correctness

### Prohibited in tests

- live OpenAI calls
- flaky timer-based polling
- dependence on external data downloads

---

## Mocking strategy

### Batch API mock boundary

Mock at the `batch_client.py` boundary.

The fake client must support:

- upload returning file IDs
- create returning batch ID and metadata
- get status returning transitional and final states
- download returning fixture file content

### Fixture recommendations

#### Input fixtures

- `small_words_snapshot/`
- `small_phrases_snapshot/`
- `small_reference_snapshot/`
- `mixed_retry_snapshot/`

#### Output fixtures

- ordered output
- scrambled output
- partial output
- output with schema failures
- output with reference localization failures

---

## Final acceptance checklist for Codex

Before concluding, Codex must verify that:

- all planned stages through Stage 9 are complete or explicitly justified if deferred
- words, phrases, and reference entries are all supported end-to-end
- tests exist for all three families
- no live API calls are required in tests
- new CLI behavior is documented
- existing CLI behavior is preserved
