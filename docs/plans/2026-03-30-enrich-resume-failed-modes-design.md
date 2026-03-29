# Enrich Resume Failed Modes Design

**Date:** 2026-03-30
**Status:** Approved design

## Goal

Add `--skip-failed` and `--retry-failed-only` to the realtime `enrich` command so operators can resume in three explicit modes:

- retry unresolved failures as part of normal resume
- skip unresolved failures during resume
- run only unresolved failures during resume

The design must preserve append-only failure history while preventing duplicate scheduling from repeated failure rows.

## Current State

`tools.lexicon.enrich.enrich_snapshot()` already supports:

- append-only `enrich.checkpoint.jsonl` for completed lexemes
- append-only `enrich.failures.jsonl` for failed lexemes
- `--resume` semantics driven by completed lexeme IDs from the checkpoint ledger

Current gaps:

- no `--skip-failed`
- no `--retry-failed-only`
- prior failures are not deduped into a current unresolved-failure set
- CLI does not validate these retry mode combinations for `enrich`

`tools.lexicon.voice_generate.run_voice_generation()` already implements the operator contract we want to mirror at a smaller scope:

- `--resume`
- `--retry-failed-only`
- `--skip-failed`
- mutual exclusion between retry-only and skip-failed
- unresolved-failure selection derived from failure ledger minus completed ledger

## Requirements

1. `enrich` gets two new flags:
   - `--skip-failed`
   - `--retry-failed-only`
2. Both flags require `--resume`.
3. The two flags are mutually exclusive.
4. `enrich.failures.jsonl` remains append-only.
5. A later success must not rewrite or delete prior failure rows.
6. Scheduling must dedupe repeated failure rows for the same lexeme.
7. Retry-only mode must support reruns with a different endpoint/model without rescheduling already-completed lexemes.

## Recommended Approach

### Completed state remains checkpoint-driven

`enrich.checkpoint.jsonl` remains the source of truth for completed lexemes. A lexeme is completed if any checkpoint row exists for its `lexeme_id`.

### Failure history remains append-only

`enrich.failures.jsonl` stays as historical evidence. Each new failed attempt appends a new row.

We do not delete or rewrite old failures after a later success.

### Unresolved failures are derived, not stored

At runtime:

- load failed `lexeme_id`s from `enrich.failures.jsonl`
- dedupe them to a set
- subtract completed `lexeme_id`s from `enrich.checkpoint.jsonl`

This produces the unresolved failure set used for scheduling.

## Resume Modes

### `--resume`

Pending lexemes are:

- all lexemes not present in `enrich.checkpoint.jsonl`

This means unresolved failures are retried by default during resume.

### `--resume --skip-failed`

Pending lexemes are:

- all lexemes not present in the checkpoint ledger
- excluding unresolved failures derived from the failure ledger

This supports forward progress when operators want to leave known-bad lexemes alone.

### `--resume --retry-failed-only`

Pending lexemes are:

- only unresolved failed lexemes
- deduped by `lexeme_id`
- excluding anything already completed in the checkpoint ledger

This supports targeted reruns with a different model, provider mode, or endpoint.

## CLI Validation Rules

Invalid combinations must fail fast before execution:

- `--retry-failed-only` without `--resume`
- `--skip-failed` without `--resume`
- `--retry-failed-only` with `--skip-failed`

## Data-Flow Summary

1. Load lexemes from snapshot inputs.
2. Load completed lexeme IDs from `enrich.checkpoint.jsonl` when `resume=True`.
3. Load failed lexeme IDs from `enrich.failures.jsonl` when `resume=True` and either retry-only or skip-failed is set.
4. Derive unresolved failure IDs as `failed - completed`.
5. Select pending lexemes according to the chosen resume mode.
6. Keep append-only writes for both checkpoint and failure ledgers.
7. On later success, rely on checkpoint membership rather than deleting failure rows.

## Why This Approach

This matches the existing `enrich` audit model and the current `voice-generate` operator contract without adding a second mutable state file.

It avoids two bad alternatives:

- destructive failure-file cleanup after success
- a second "active failures" ledger that can drift from checkpoint and output state

## Files Likely To Change

- `tools/lexicon/cli.py`
- `tools/lexicon/enrich.py`
- `tools/lexicon/tests/test_enrich.py`
- `tools/lexicon/tests/test_cli.py`
- `tools/lexicon/README.md`
- `docs/status/project-status.md`

## Verification Scope

Focused verification is sufficient for this slice:

- `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q`

No backend, frontend, or e2e changes are expected.
