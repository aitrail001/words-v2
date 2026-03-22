# Lexicon Batch Enrichment

This is the operator-facing runbook for the offline batch-first lexicon pipeline.

## Canonical Pipeline

The legacy deterministic pipeline remains supported:

`build-base` -> `enrich` -> `validate` -> `compile-export` -> `import-db`

The batch slice now sits alongside that path and uses JSONL ledgers inside a snapshot directory.

## Batch Commands

### `batch-prepare`

Build deterministic request rows from a normalized snapshot seed file.

### `batch-submit`

Record a submitted batch job ledger from `batch_requests.jsonl`.

### `batch-status`

Summarize request, job, result, and QC counts for a snapshot directory.

### `batch-ingest`

Convert a completed batch output JSONL file into `batch_results.jsonl`.

### `batch-retry`

Create retry requests for failed rows and append them with bumped attempt numbers.

### `batch-qc`

Produce deterministic QC verdict rows and a review queue from ingested results.

### `review-apply`

Apply approved manual overrides to an existing QC verdict file and refresh the review queue.

## Snapshot Artifacts

Expected files in a batch-enabled snapshot directory:

```text
snapshot/
  batch_requests.jsonl
  batch_jobs.jsonl
  batch_results.jsonl
  batch_qc.jsonl
  enrichment_review_queue.jsonl
  batches/
  words.enriched.jsonl
  phrases.enriched.jsonl
  references.enriched.jsonl
  <compiled-output>.review_qc.jsonl
  <compiled-output>.review_queue.jsonl
```

Reference, phrase, and word families remain separate input sources. All joins across prepare, submit, ingest, retry, and QC use `custom_id`.

`compile-export` now writes family-aware compiled outputs when the corresponding snapshot source files exist. `import-db` can dry-run those directory layouts and count the families, and the backend schema now supports phrase and reference writes as well.

`batch-qc` produces the initial flagged review queue, and `review-apply` replays approved overrides onto the persisted QC verdict rows before the next compile/import pass.

Realtime exports now emit artifact-specific sidecars such as `words.enriched.review_qc.jsonl` and `words.enriched.review_queue.jsonl` through the same shared review-prep logic that batch QC uses. That gives `word`, `phrase`, and `reference` artifacts the same deterministic warning labels, review priority, and queue semantics before human review, without forcing realtime runs through batch transport ledgers.

## Compiled Review Staging

The shipped admin review path for compiled learner-facing artifacts is DB-backed staging, not final publish.

Flow:

1. Compile a learner-facing JSONL artifact such as `words.enriched.jsonl`
2. Import that artifact into the admin compiled-review surface at `/lexicon/compiled-review`
3. Review rows in the admin UI
4. Export one or more JSONL outputs:
   - approved compiled rows
   - rejected overlays
   - regenerate rows
   - canonical review decisions
5. Run `review-materialize` if you want a purely file-based materialization step from canonical decisions
6. Feed approved rows into `import-db`

Important:

- The compiled-review import writes to dedicated review-staging tables, not to final word/meaning/reference tables.
- Final lexicon data is still written only by `import-db`.
- Review decisions remain an overlay on immutable compiled artifacts.
