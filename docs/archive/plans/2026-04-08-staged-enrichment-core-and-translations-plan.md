# Staged Enrichment Core And Translations Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split lexicon enrichment into a core English stage and a translation stage while keeping review and import workflows reading the existing merged `words.enriched.jsonl` artifact.

**Architecture:** Add a new stage-1 core artifact plus a stage-2 translation ledger, then merge them back into the existing compiled learner-row shape. Preserve current downstream commands and snapshot conventions while introducing a one-time migration path for legacy merged artifacts.

**Tech Stack:** Python CLI in `tools/lexicon`, JSONL snapshot artifacts, existing compile/review/import pipeline, pytest-based lexicon tests.

---

## Scope

- Add a core enrichment stage that emits English-only learner data.
- Add a translation stage that emits locale-scoped translation rows keyed to compiled senses.
- Add a merge step that rebuilds the existing merged learner JSONL artifact.
- Add a migration command to split existing merged artifacts into staged artifacts.
- Keep `review-materialize`, review prep/QC, and `import-db` consuming merged `words.enriched.jsonl`.

Out of scope for this slice:

- changing review/import to consume partial staged artifacts directly
- redesigning translation QC heuristics beyond what is needed to make the staged contract workable
- adding new target locales beyond the current required set

## Artifact Model

### New staged artifacts

- `words.enriched.core.jsonl`
  - one row per compiled entry
  - contains all current compiled learner fields except `translations`
  - preserves `entry_id`, `sense_id`, `generation_run_id`, model metadata, and any fields needed for deterministic merge

- `words.translations.jsonl`
  - one row per `entry_id + sense_id + locale`
  - fields: `entry_id`, `sense_id`, `locale`, `definition`, `usage_note`, `examples`, `generation_run_id`, `model_name`, `generated_at`, `status`

### Existing merged artifact retained

- `words.enriched.jsonl`
  - remains the merged downstream contract
  - review and import keep reading this file

## File Map

### Primary implementation files

- Modify: `tools/lexicon/enrich.py`
  - split generation flows
  - add staged writers and merge helpers
  - keep existing merged contract builder

- Modify: `tools/lexicon/cli.py`
  - add new commands
  - wire staged pipeline options

- Modify: `tools/lexicon/compile_export.py`
  - support merging compiled core rows with translation ledger rows into current final shape

- Modify: `tools/lexicon/validate.py`
  - add staged artifact validation entry points where needed

- Modify: `tools/lexicon/review_prep.py`
  - likely no behavior change, but verify assumptions that merged artifact still matches current contract

- Modify: `tools/lexicon/import_db.py`
  - likely no behavior change, but verify merged artifact compatibility

### Schema / contract helpers

- Modify: `tools/lexicon/schemas/word_enrichment_schema.py`
  - support core-stage payload without translations if stage-1 uses strict schema

- Modify: `tools/lexicon/contracts.py`
  - add translation-ledger helpers or staged normalization utilities if shared validation belongs here

### Tests

- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/tests/test_validate.py`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_review_materialize.py`
- Add or modify fixtures under `tools/lexicon/tests/fixtures/` if staged artifact samples are needed

### Documentation

- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

## Command Surface

### New commands

- `enrich-core`
  - reads snapshot lexemes/senses
  - writes `words.enriched.core.jsonl`
  - uses new core-only provider/schema path

- `enrich-translations`
  - reads `words.enriched.core.jsonl`
  - writes `words.translations.jsonl`
  - translation-only prompt and retries

- `merge-enrich`
  - reads `words.enriched.core.jsonl` and `words.translations.jsonl`
  - writes merged `words.enriched.jsonl`

- `split-enrich-artifact`
  - one-time migration command
  - reads legacy merged `words.enriched.jsonl`
  - writes staged artifacts

### Existing command compatibility

- Keep current `enrich` command during rollout.
- First rollout option: make `enrich` remain untouched while staged commands are used explicitly.
- Later option, after staged flow is stable: let `enrich` orchestrate `enrich-core -> enrich-translations -> merge-enrich`.

## Implementation Tasks

### Task 1: Define staged artifact contracts

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/contracts.py`
- Test: `tools/lexicon/tests/test_enrich.py`

- [ ] Define helper types or row builders for core compiled rows and translation ledger rows.
- [ ] Decide whether translation ledger rows are keyed by `sense_id` alone or by `entry_id + sense_id + locale`; prefer all three for explicitness.
- [ ] Add deterministic merge helpers that reconstruct the current compiled `translations` object from ledger rows.
- [ ] Add unit tests for:
  - merging complete translations into a core row
  - stable ordering of merged locales/examples
  - missing translation rows staying out of the final artifact unless explicitly allowed

### Task 2: Add core-only enrichment generation

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/schemas/word_enrichment_schema.py`
- Test: `tools/lexicon/tests/test_enrich.py`

- [ ] Introduce a core-only prompt/schema path that removes translation requirements from stage 1.
- [ ] Reuse existing word decision, phonetics, senses, English definitions, examples, forms, and usage note generation.
- [ ] Ensure core output preserves all information needed for review/import after merge.
- [ ] Add tests covering:
  - stage-1 provider payload normalization without translations
  - core artifact writing and resume semantics
  - compile compatibility with current merged row builder after later merge

### Task 3: Add translation-only generation

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/contracts.py`
- Test: `tools/lexicon/tests/test_enrich.py`

- [ ] Add translation-only prompt builder that takes English sense fields and asks only for localized `definition`, `usage_note`, and aligned example translations.
- [ ] Write translation ledger rows instead of overwriting compiled learner rows.
- [ ] Support retries and resume by `entry_id + sense_id + locale`.
- [ ] Add tests covering:
  - translation ledger writes
  - resume behavior when some locales already exist
  - retry behavior on translation-only failures
  - merge result from core + translations matching old artifact shape

### Task 4: Add merge command

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/validate.py`
- Test: `tools/lexicon/tests/test_cli.py`
- Test: `tools/lexicon/tests/test_validate.py`

- [ ] Add `merge-enrich` command that rebuilds `words.enriched.jsonl`.
- [ ] Make merged output deterministic and idempotent.
- [ ] Decide merge behavior when translations are incomplete:
  - recommended for initial rollout: require all required locales before emitting a merged row to the final artifact
  - alternatively emit only fully translated rows and report missing translation coverage
- [ ] Add tests for:
  - complete merge success
  - missing locale failure/reporting
  - repeated merge producing byte-stable row ordering

### Task 5: Add migration command for legacy snapshots

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_cli.py`
- Test: `tools/lexicon/tests/test_enrich.py`

- [ ] Add `split-enrich-artifact`.
- [ ] Read legacy merged `words.enriched.jsonl`.
- [ ] Write `words.enriched.core.jsonl` and `words.translations.jsonl`.
- [ ] Preserve metadata such as `generation_run_id`, `model_name`, `generated_at`, and sense ordering.
- [ ] Add tests for:
  - exact row-count preservation across split + merge roundtrip
  - idempotent reruns
  - legacy artifacts with multiple senses and all locales

### Task 6: Verify downstream compatibility

**Files:**
- Modify: `tools/lexicon/review_prep.py` if needed
- Modify: `tools/lexicon/import_db.py` only if compatibility gaps appear
- Test: `tools/lexicon/tests/test_review_materialize.py`
- Test: `tools/lexicon/tests/test_import_db.py`

- [ ] Run downstream tests against merged output from staged artifacts.
- [ ] Confirm review prep still surfaces translations from merged artifact without code changes if possible.
- [ ] Confirm `import-db` still accepts merged rows unchanged.
- [ ] Only patch downstream code if merge output cannot be made contract-identical.

### Task 7: Document operator workflow

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

- [ ] Document explicit staged workflow:
  - `enrich-core`
  - `enrich-translations`
  - `merge-enrich`
  - `review-materialize`
  - `import-db`
- [ ] Document one-time migration flow for existing snapshots.
- [ ] Update project status with evidence once the staged path is implemented and verified.

## Verification Plan

- Unit tests for staged artifact builders and merge helpers
- CLI tests for new commands
- Roundtrip test:
  - split legacy merged artifact
  - merge staged artifacts
  - compare with original merged rows
- Bounded smoke test on a small snapshot subset using:
  - `enrich-core`
  - `enrich-translations`
  - `merge-enrich`
- Validate that merged output still passes existing compiled validation and review/import tests

## Acceptance Criteria

- Stage 1 can produce core learner rows without translations.
- Stage 2 can translate from stage-1 rows without regenerating English/core data.
- `merge-enrich` can rebuild a merged artifact compatible with current review/import workflows.
- `split-enrich-artifact` can migrate existing merged snapshots into staged artifacts.
- Existing downstream review/import commands continue to work against merged output.

## Risks

- Current compiled row shape may embed translation assumptions more deeply than expected.
- Sense identity must remain stable across stage 1, stage 2, migration, and merge.
- Resume semantics must be handled separately for core rows and translation rows to avoid new artifact drift.
- Translation QC may need follow-up hardening after the staged pipeline lands.
