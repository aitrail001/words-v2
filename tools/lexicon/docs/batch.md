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
```

Reference, phrase, and word families remain separate input sources. All joins across prepare, submit, ingest, retry, and QC use `custom_id`.

`compile-export` now writes family-aware compiled outputs when the corresponding snapshot source files exist. `import-db` can dry-run those directory layouts and count the families, and the backend schema now supports phrase and reference writes as well.

`batch-qc` produces the initial flagged review queue, and `review-apply` replays approved overrides onto the persisted QC verdict rows before the next compile/import pass.
