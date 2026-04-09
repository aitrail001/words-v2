# Lexicon Admin Workflow Streamlining Design

**Date:** 2026-03-22

## Goal

Make the admin portal present one clear lexicon workflow:

1. identify or build a snapshot
2. review the compiled artifact
3. export or materialize approved rows
4. import approved rows into the final DB
5. verify the final DB state

The portal should stop behaving like a loose collection of overlapping tools and instead explain what the current stage is, what artifacts exist, what the next valid action is, and which steps still happen outside the portal.

## Current Problems

The current admin flow is operationally correct but still fragmented.

### Flat route model instead of workflow model

- `/lexicon/ops` exists, but it behaves more like a launch pad than a workflow shell.
- global navigation presents `Lexicon Ops`, `Compiled Review`, `JSONL Review`, `Import DB`, `DB Inspector`, and `Legacy` as flat peers.
- `/lexicon` and `/lexicon/legacy` still preserve the older staged-selection review flow strongly enough that it competes with the current compiled-artifact workflow.

### Inconsistent input model

- some pages are snapshot-driven (`/lexicon/ops`)
- some are file-upload driven (`/lexicon/compiled-review`)
- some are path-driven (`/lexicon/jsonl-review`, `/lexicon/import-db`)
- the same operator has to mentally translate between snapshot, artifact, file path, and DB state

### Missing workflow state in the UI

The portal does not clearly show:

- current stage
- current snapshot
- active artifact
- whether the snapshot is review-ready
- whether the snapshot is import-ready
- what the next recommended action is

### Hidden outside-portal dependency

The actual lexicon execution pipeline still depends on offline CLI steps:

- `build-base`
- optional ambiguous-form adjudication
- `enrich`
- `validate`
- `compile-export`
- batch prepare/submit/status/ingest/qc where relevant

The admin portal depends on those outputs, but it does not state this clearly enough inside the UI.

## Design Principles

- `Lexicon Ops` is the canonical entrypoint.
- `Compiled Review` is the default review mode.
- `JSONL Review` remains available as an alternative, not the default branch.
- standalone pages remain available for direct operator use.
- snapshot and artifact context should carry across pages consistently.
- the portal must explicitly distinguish:
  - snapshot artifacts
  - review state
  - final import inputs
  - final DB state
- CLI-only steps should be shown, not hidden.
- final DB import remains explicit and separate from review approval.

## Recommended Information Architecture

### Primary routes

- `/lexicon/ops`
  - canonical workflow shell
- `/lexicon/compiled-review`
  - default review stage
- `/lexicon/jsonl-review`
  - alternate review stage
- `/lexicon/import-db`
  - explicit final publish/import stage
- `/lexicon/db-inspector`
  - final-state verification stage
- `/lexicon/legacy`
  - deprecated staged-selection tooling

### Navigation model

Primary lexicon navigation should emphasize the workflow order:

- `Lexicon Ops`
- `Compiled Review`
- `JSONL Review`
- `Import DB`
- `DB Inspector`

`Legacy` should not remain a first-class peer in the primary workflow. It should be reachable, but visually demoted behind a `Legacy Tools` or equivalent utility entry.

The admin home page should frame `Lexicon Ops` as the main lexicon surface and describe the other pages as workflow stages or alternate entrypoints.

## Workflow Shell

`/lexicon/ops` should become the lexicon workflow shell.

### Required elements

1. snapshot list
2. selected snapshot summary
3. workflow stage rail
4. next recommended action
5. alternate action
6. artifact readiness panel
7. outside-portal steps panel
8. final import panel

### Stage rail

Show the workflow stages explicitly:

1. `Build Snapshot`
2. `Review Compiled Artifact`
3. `Export Approved Rows`
4. `Import Final DB`
5. `Verify DB`

The selected snapshot should highlight the current stage and the next recommended step.

### Snapshot readiness model

The selected snapshot should derive a stage from artifact presence.

Example rules:

- `lexemes.jsonl` / `senses.jsonl` present, no compiled artifact:
  - stage = `Build Snapshot`
- `words.enriched.jsonl` or family-aware compiled artifact present, no approved rows:
  - stage = `Review Compiled Artifact`
- `approved.jsonl` present:
  - stage = `Import Final DB`
- final DB import completed and verified:
  - stage = `Verify DB`

Batch snapshots should still use the same top-level workflow stages, even though they have additional transport artifacts.

### Next action model

For the selected snapshot:

- if compiled artifact exists:
  - primary CTA = `Open Compiled Review`
  - secondary CTA = `Open JSONL Review`
- if `approved.jsonl` exists:
  - primary CTA = `Open Import DB`
- if import already ran:
  - CTA = `Open DB Inspector`

This makes the workflow branch explicit instead of forcing the operator to choose from equal peers.

## Standard Snapshot and Artifact Vocabulary

The UI should consistently classify artifacts as:

### Snapshot build artifacts

- `lexemes.jsonl`
- `senses.jsonl`
- `concepts.jsonl`
- `canonical_entries.jsonl`
- `canonical_variants.jsonl`
- `generation_status.jsonl`
- `ambiguous_forms.jsonl`
- `form_adjudications.jsonl`
- `enrichments.jsonl`
- `enrich.checkpoint.jsonl`
- `enrich.failures.jsonl`

### Legacy staged-selection artifacts

- `selection_decisions.jsonl`
- `review_queue.jsonl`

### Compiled artifacts

- `words.enriched.jsonl`
- `phrases.enriched.jsonl`
- `references.enriched.jsonl`
- `words.mode-c-safe.enriched.jsonl`

### Review-prep sidecars

- `<compiled-output>.review_qc.jsonl`
- `<compiled-output>.review_queue.jsonl`

### Review outputs

- `approved.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`
- `review.decisions.jsonl`

### Batch transport artifacts

- `batch_requests.jsonl`
- `batch_jobs.jsonl`
- `batch_results.jsonl`
- `batch_qc.jsonl`
- `enrichment_review_queue.jsonl`

The UI should label which of these are:

- generated by CLI
- used for review
- used for import
- used only for audit or troubleshooting

## Standalone Page Responsibilities

### Compiled Review

This remains the default review mode.

It should:

- support direct file upload
- also support snapshot-driven import by artifact path
- display snapshot context when opened from `Lexicon Ops`
- show its place in the stage rail
- show next step:
  - `Export approved rows`
  - then `Open Import DB`

The key gap to fix is that `Ops -> Compiled Review` should not merely open the page. It should carry the selected snapshot and artifact in a way the page can actually use.

### JSONL Review

This remains the alternate review mode.

It should:

- keep artifact path, decisions path, and output directory entry
- load directly from snapshot-provided artifact paths when opened from `Ops`
- display snapshot context and stage context
- show the same next-step guidance as `Compiled Review`

### Import DB

This remains explicit and separate from review.

It should:

- prefer `approved.jsonl` automatically when available
- show where the approved artifact came from
  - compiled-review export
  - JSONL-only materialize
- always encourage dry-run before real import
- show that this is the canonical final DB write step

### DB Inspector

This should be framed as:

- final DB verification
- inspection of already imported rows
- not part of review staging

It should display the current stage and explain that the data shown here is already live in the final DB.

### Legacy

This should remain accessible but clearly demoted.

It should be presented as:

- deprecated
- older staged-selection workflow
- not the canonical compiled-artifact review path

## Outside-Portal Steps

The admin portal should explicitly show which steps remain CLI-only today.

`Lexicon Ops` should include an `Outside Portal` panel with:

- step name
- current readiness
- expected artifact
- command reference or doc link

For the realtime/offline compiled path:

- `build-base`
- optional ambiguous-form adjudication
- `enrich`
- `validate`
- `compile-export`

For batch:

- `batch-prepare`
- `batch-submit`
- `batch-status`
- `batch-ingest`
- `batch-qc`

This is important because the admin portal is currently a review/inspection layer on top of an offline execution pipeline. The product should say that plainly.

## Backend/API Changes

### `lexicon_ops` should expose workflow metadata

The current snapshot summary is too thin. It should derive and return:

- current workflow stage
- next recommended action
- available compiled artifacts by family
- preferred review artifact
- preferred import artifact
- CLI-only steps still outstanding

This should be derived metadata, not hardcoded frontend heuristics.

### `compiled-review` should support import-by-path

The current compiled-review surface is upload-only. That works for standalone use, but it is a bad fit for snapshot-first workflow.

Add a snapshot/path-driven import path so `Lexicon Ops` can launch the default review mode against an existing compiled artifact without forcing the operator to re-upload a file that already exists on the server.

### `jsonl-review` path model can stay, but should be made more snapshot-aware

The current path-driven model is acceptable because it is the alternate/manual path, but the API and page should accept snapshot context and preserve it in the response/UI.

### `import-db` should keep the current explicit API model

The current explicit dry-run and run endpoints are directionally correct. The main improvement is to make them workflow-aware through better prefill and context, not to collapse them into review.

## Documentation Changes

The portal should link directly to:

- current lexicon operator flow
- what still happens outside admin
- canonical final DB write path

The docs should be revised so the same workflow language appears in:

- `tools/lexicon/OPERATOR_GUIDE.md`
- `tools/lexicon/docs/batch.md`
- admin page copy
- status board entries

## Testing Strategy

### Frontend

- `Lexicon Ops` stage rail and next-action rendering
- snapshot context headers on standalone pages
- prefilled snapshot/artifact behavior across pages
- legacy route demotion in nav
- outside-portal instruction rendering

### Backend

- `lexicon_ops` workflow-stage derivation
- preferred review/import artifact selection
- compiled-review import-by-path safety and success
- import path safety remains intact

### E2E

- `Ops -> Compiled Review` with snapshot-carried context
- `Ops -> JSONL Review` with preloaded artifact
- `Ops -> Import DB` with approved artifact prefilled
- `Ops -> DB Inspector` as final verification step

## Recommendation

Do not build a single wizard page. Keep the separate route surfaces, but make `Lexicon Ops` the workflow shell and the source of truth for:

- where the operator is
- which artifacts matter
- what step comes next
- what still must be done outside the portal

That solves the current confusion without removing the power-user entrypoints.
