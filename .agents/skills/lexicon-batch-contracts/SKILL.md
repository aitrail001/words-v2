---
name: lexicon-batch-contracts
description: Use when working on lexicon batch request/result contracts, custom_id schemes, shard metadata, and JSONL artifact boundaries.
---

# Lexicon Batch Contracts

Use this skill when changing batch request or ingestion artifacts in `tools/lexicon`.

## Rules

- Keep JSONL as the canonical offline format.
- Treat `custom_id` as the stable join key across prepare, submit, ingest, retry, QC, and review.
- Do not change accepted artifact shapes without a documented migration.
- Preserve deterministic selection and resumability.
- Keep word, phrase, and reference entries as separate families.

## Checks

- Verify request/result round-trips.
- Verify out-of-order ingestion.
- Verify retries append attempts rather than overwrite accepted outputs.
