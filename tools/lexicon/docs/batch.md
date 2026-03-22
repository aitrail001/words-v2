# Lexicon Batch Enrichment

This document covers the active batch contract for the lexicon tool.

## What batch means here

Batch is a deferred file-based workflow:

1. prepare request JSONL from a snapshot
2. run generation separately
3. ingest completed output JSONL later
4. materialize accepted rows into `words.enriched.jsonl`
5. send failures to `words.regenerate.jsonl`

The current tool supports the batch artifact contract directly. It does not yet implement a full remote OpenAI Batch API submit/poll/download transport.

## Batch pipeline

```text
build-base -> batch-prepare -> external generation -> batch-ingest -> review -> import-db
```

Realtime and batch share the same word-level validation/materialization rules. The difference is timing:

- realtime validates immediately after each LLM response
- batch validates when completed result files are ingested

## Commands

### `batch-prepare`

Build request rows from a snapshot.

Writes:

- `batch_requests.jsonl`

### `batch-submit`

Records local job ledger metadata.

Writes:

- `batch_jobs.jsonl`

This is bookkeeping only in the current implementation.

### `batch-status`

Summarizes request/job/result/materialization counts for a snapshot.

### `batch-ingest`

Ingests completed output JSONL and writes:

- `batch_results.jsonl`
- accepted rows to `words.enriched.jsonl`
- failed rows to `words.regenerate.jsonl`

### `batch-retry`

Builds retry request rows for failed items.

## Snapshot files used by batch

```text
snapshot/
  lexemes.jsonl
  batch_requests.jsonl
  batch_jobs.jsonl
  batch_results.jsonl
  words.enriched.jsonl
  words.regenerate.jsonl
  reviewed/approved.jsonl
  reviewed/rejected.jsonl
  reviewed/regenerate.jsonl
  reviewed/review.decisions.jsonl
```

The active batch flow does not depend on:

- `senses.jsonl`
- `concepts.jsonl`
- `selection_decisions.jsonl`
- `review_queue.jsonl`
- `compile-export`

## Review and import

After `batch-ingest`:

1. review `words.enriched.jsonl` in `/lexicon/compiled-review` or `/lexicon/jsonl-review`
2. export/materialize `reviewed/approved.jsonl`
3. import that reviewed output through `import-db`
4. inspect the result in `/lexicon/db-inspector`
