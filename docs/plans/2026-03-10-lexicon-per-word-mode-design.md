# Lexicon Per-Word Enrichment + Mode C Filtering Design

**Date:** 2026-03-10

**Status:** Approved design for implementation in `feat_lexicon_word_mode_review_ui_20260310`

## Goal

Evolve the lexicon admin tool from a purely per-sense enrichment pipeline into a mixed-mode pipeline that supports:

1. a new **per-word enrichment mode** with bounded parallelism,
2. a **first-class Mode C compile path** that can safely compile only importable words,
3. a clearer **admin review UI** that exposes enough sense-selection evidence for human review,
4. test, CI, and operator documentation coverage strong enough to ship and maintain the workflow.

The immediate practical target is to make large staged runs, such as `2,000` words and beyond, operationally realistic without removing the existing compatibility path.

## Current State

### Lexicon pipeline

The current lexicon flow is:

- `build-base` selects bounded learner-facing senses for each lexeme
- `enrich` iterates **per sense** and produces one `EnrichmentRecord` per `sense_id`
- `compile-export` joins lexemes, senses, and enrichments into one compiled word record per lemma
- `import-db` writes compiled records into the main local DB tables

Operationally, this means a `2,000`-word run expands to enrichment calls for all selected senses rather than words. In the current staged test, `2,000` words expanded to `7,546` selected senses.

### Review flow

The staged review branch exists and is useful, but it is still shaped around raw `selection_decisions.jsonl` storage. Reviewers currently lack a strong comparison surface for:

- deterministic selected senses,
- reranked senses,
- candidate sense definitions/glosses,
- ranking hints/reasons,
- review override implications.

### Mode C gap

Mode C is conceptually supported by the architecture but not yet first-class in the CLI. Today, operators can create the split manually, but `compile-export` cannot natively filter by review state or decisions artifacts.

## Requirements

### Functional requirements

1. Keep the current per-sense enrichment path available as a compatibility fallback.
2. Add a new per-word enrichment mode that sends one LLM request per word containing all selected senses for that word.
3. Support bounded parallelism for the new per-word enrichment mode.
4. Preserve deterministic output ordering and stable IDs so downstream compile/import behavior stays predictable.
5. Add first-class compile filtering so operators can build an importable output from the safe subset of a staged review run.
6. Improve the admin review UI so reviewers can make decisions from the page without needing to inspect raw JSONL.
7. Extend automated test coverage across tool, backend, frontend, and E2E layers.
8. Update operator and status documentation.

### Non-functional requirements

1. Maintain backward compatibility where practical.
2. Keep secrets and LLM configuration in environment variables only.
3. Avoid introducing real large-batch LLM execution into CI.
4. Fail loudly on malformed per-word responses rather than silently degrading.
5. Keep the review branch separate from the final import branch unless explicitly published.

## Approaches Considered

### Approach A: Parallelize per-sense only

Add bounded concurrency to the current per-sense path, add Mode C compile filtering, and improve the review UI.

**Pros**

- smallest code change,
- lowest schema disruption,
- easiest short-term regression risk profile.

**Cons**

- still too many LLM calls long-term,
- duplicates word-level context across senses,
- weak coherence across senses of the same word,
- does not materially improve the long-term `20k+` operator story.

### Approach B: Additive per-word mode + parallelism + Mode C filtering

Add a new per-word enrichment mode while keeping the current per-sense mode available. Add bounded per-word concurrency, first-class Mode C compile filtering, and improved review UX.

**Pros**

- strongest long-term direction without a destructive migration,
- significantly reduces request count for large runs,
- lets the model see all selected senses for a word at once,
- preserves compatibility and fallback behavior.

**Cons**

- larger implementation slice,
- requires new response validation and compile integration,
- more cross-cutting tests.

### Approach C: Replace per-sense with per-word everywhere

Hard-switch the lexicon pipeline to per-word enrichment immediately.

**Pros**

- cleanest future architecture.

**Cons**

- too much migration risk for one PR,
- makes rollback harder,
- increases the blast radius across tooling, tests, and docs.

## Chosen Approach

Use **Approach B**.

This gives the project a scalable operator path while keeping a stable fallback. It also lets us ship the review UX and Mode C operational improvements in the same slice instead of treating them as unrelated work.

## Proposed Architecture

## 1. Enrichment modes

Add explicit enrichment modes:

- `per_sense` — current behavior, retained for fallback/debugging
- `per_word` — new behavior, one request per word containing all selected senses

CLI direction:

- `python3 -m tools.lexicon.cli enrich --snapshot-dir ... --mode per_sense`
- `python3 -m tools.lexicon.cli enrich --snapshot-dir ... --mode per_word --max-concurrency 8`

The initial default should remain conservative unless the implementation proves stable enough to promote later.

## 2. Per-word enrichment request/response model

### Input

For each lexeme, the prompt will include:

- `lemma`
- `wordfreq_rank`
- all selected senses for that lexeme, each with:
  - `sense_id`
  - `part_of_speech`
  - `wn_synset_id`
  - `canonical_gloss`
  - `sense_order`

### Output

The model will return JSON for the word containing:

- optional shared word-level fields if needed later,
- a `senses` array,
- one item per provided `sense_id`,
- learner-facing fields for each sense.

Hard constraints:

- no invented senses,
- no omitted senses unless the schema explicitly permits a refusal with an error,
- returned senses must map to provided `sense_id` values,
- response must remain grounded in the selected input senses only.

## 3. Parallelism model

Parallelism should be applied **across words**, not across senses within one word.

Behavior:

- bounded concurrency via CLI flag,
- deterministic write ordering preserved after parallel execution,
- transient failures retried a small fixed number of times,
- final run exits non-zero if any word remains unprocessed,
- error summary includes failed lemmas and causes.

This keeps concurrency operationally useful without making outputs nondeterministic.

## 4. Artifact model

The existing `enrichments.jsonl` file should remain supported for `per_sense` mode.

For `per_word` mode, introduce a dedicated word-level artifact rather than overloading the current sense-level file. Recommended artifact:

- `word_enrichments.jsonl`

Each row should include:

- `snapshot_id`
- `lexeme_id`
- `lemma`
- `generation_run_id`
- `model_name`
- `prompt_version`
- `generated_at`
- `confidence_summary` or equivalent top-level metadata
- `senses[]` keyed by `sense_id`

`compile-export` should learn to consume either:

- classic `enrichments.jsonl`, or
- new `word_enrichments.jsonl`

This preserves compatibility while making the artifact boundaries clear.

## 5. Mode C first-class compile filtering

Add explicit compile-time support for decisions-aware filtering.

### Inputs

`compile-export` should optionally accept:

- `--decisions <path>`
- optional inclusion/filter flags or a preset

### Recommended operator preset

Add a preset for the safe direct-import subset, conceptually:

- `--decision-filter mode_c_safe`

Semantics:

- include `risk_band=deterministic_only`,
- include `auto_accepted=true`,
- exclude `review_required=true`,
- optionally include explicitly approved review items later if a review-state input is supplied.

This removes the need for manual split scripts and makes the hybrid path reproducible.

## 6. Review UI improvements

The admin review UI should present a real reviewer decision surface.

### Reviewer information to display clearly

For each review item:

- lemma, frequency rank, risk band, selection risk score,
- deterministic selected senses,
- reranked selected senses if present,
- candidate senses with card/table layout showing:
  - `wn_synset_id`
  - part of speech
  - canonical label if present
  - gloss/definition
  - current selection status
  - ranking hints from candidate metadata
  - any deterministic/rerank reason fields available,
- review override UI with readable multi-select behavior,
- review comment,
- preview/publish consequences where relevant.

### UI layout direction

Recommended layout:

1. summary strip,
2. current selection panel,
3. candidate comparison panel,
4. reviewer override panel,
5. publish preview panel.

The key improvement is readability and scanability, not more raw JSON.

## 7. Backend/API adjustments

The backend should support the improved UI with clearer response shaping where needed.

Preferred direction:

- keep persisted review rows backward compatible,
- add normalized response helpers for candidate metadata if raw payload shape is too awkward for the UI,
- avoid exposing unnecessary internal structure if it can be pre-shaped server-side.

Auth and admin-only requirements remain unchanged.

## 8. Compile/import interaction with review

This feature does **not** collapse the review and import paths into one.

The intended flows remain:

### Direct import path

- `build-base`
- `score-selection-risk`
- optional `prepare-review`
- `enrich --mode per_word` on the safe subset
- `compile-export --decisions ... --decision-filter mode_c_safe`
- `import-db`

### Staged review path

- `build-base`
- `score-selection-risk`
- optional `prepare-review`
- import `selection_decisions.jsonl` into staged review tables
- reviewer approves/rejects
- later publish and/or enrich approved risky words in a future fuller workflow

## Error handling

### Per-word enrichment

- schema validation failure for a word should fail that word explicitly,
- the run summary should list failed words,
- parallel workers must not corrupt output ordering,
- output should not partially write malformed rows.

### Mode C compile filtering

- missing decisions file when filter requested should be a hard error,
- references to lexeme IDs not present in the snapshot should be surfaced,
- empty filtered result should be reported clearly.

### Review UI

- long candidate metadata should wrap or scroll cleanly,
- reviewer actions should show clear loading/error states,
- publish preview should remain separate from final publish.

## Testing Strategy

### Lexicon tool

- unit tests for per-word prompt building,
- unit tests for per-word response validation,
- unit tests for per-word parallel ordering and failure handling,
- compile-export tests for word-level enrichment inputs,
- compile-export tests for decisions-aware filtering,
- regression tests ensuring `per_sense` remains valid.

### Backend

- review API tests for candidate metadata / item detail shape,
- publish-preview / publish tests remain green,
- any new response helper behavior covered in backend tests.

### Admin frontend

- render tests for candidate cards/table,
- interaction tests for review overrides and comments,
- tests that long candidate metadata is readable and not collapsed into unusable text.

### E2E

- extend admin staged review smoke to assert reviewer-visible candidate detail,
- keep auth and publish smoke green,
- optionally add a tool/operator smoke around decisions-aware compile filtering if feasible without real LLM dependence.

### CI

- keep large real LLM runs out of CI,
- run deterministic tool tests,
- run backend/admin/frontend/E2E checks sufficient to cover this slice,
- update workflows only if the new tests need additional commands.

## Documentation Impact

The implementation must update:

- `tools/lexicon/README.md`
- `tools/lexicon/OPERATOR_GUIDE.md`
- `docs/status/project-status.md`

Likely additional documentation:

- implementation plan in `docs/plans/`
- possibly an ADR if the project wants to formalize per-word enrichment as the preferred future architecture.

## Out of Scope

This slice does not attempt to:

- redesign the main learner-facing DB schema completely,
- run full `20k` enrichment in CI,
- force the staged review publish path to emit the full future learner-facing enriched schema,
- remove the existing per-sense compatibility path.

## Success Criteria

This design is successful when all of the following are true:

1. Operators can run `enrich` in a new `per_word` mode with bounded concurrency.
2. Operators can compile the safe Mode C subset without manual split scripts.
3. Reviewers can clearly inspect candidate senses and make decisions in the admin UI.
4. Existing per-sense fallback behavior remains available.
5. Automated tool, backend, frontend, E2E, and CI verification are updated and passing.
6. The work lands through a normal branch/PR/merge/cleanup workflow with documentation updated.
