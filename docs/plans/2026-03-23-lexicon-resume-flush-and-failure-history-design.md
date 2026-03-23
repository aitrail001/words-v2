# Lexicon Resume Flush And Failure History Design

Date: 2026-03-23
Owner: Codex

## Goal

Fix realtime per-word lexicon enrichment so completed lexemes are durably flushed to the canonical artifact set as soon as they finish, even when an earlier lexeme has already failed, and preserve append-only failure history across `--resume`.

## Live Problem

In the live phrase snapshot `phrases-7488-20260323-reviewed-phrasals-idioms-v1`:

- `enrich.log` continued to show new `lexeme-start` events
- `enrich.checkpoint.jsonl` and `words.enriched.jsonl` stopped advancing after the first failed lexeme in the ordered stream
- the process was still running

This created a misleading state where successful later lexemes could exist only in memory until process exit.

## Root Cause

The current per-word pipeline stores successful outcomes in an in-memory `completed_results` map and only writes canonical rows through `flush_completed()`.

That flush logic walks lexemes in sorted order and stops at the first lexeme that is neither already checkpointed nor present in `completed_results`.

If an earlier lexeme fails:

- no completed outcome exists for that position
- ordered flush stops at that gap
- later successful lexemes remain buffered in memory
- checkpoint, decisions, and compiled output stop advancing

The current code only backfills those buffered completions at the very end of the invocation.

## Required Behavior

### Immediate Success Durability

When a lexeme finishes successfully in per-word mode, the tool must immediately append its canonical rows to:

- `words.enriched.jsonl`
- `enrich.decisions.jsonl`
- `enrich.checkpoint.jsonl`

This must not wait for earlier lexemes to succeed, fail, or for the process to exit.

Canonical artifact order may therefore reflect completion order rather than lexeme sort order. Durability is more important than preserving ordered output in this path.

### Resume Semantics

`--resume` should continue to use `enrich.checkpoint.jsonl` as the authoritative skip ledger:

- checkpointed lexeme: skip
- not checkpointed: eligible to run

This includes lexemes that failed in an earlier attempt and later succeeded. The later success should append normal decision/checkpoint/output rows and cause future resumes to skip that lexeme.

### Failure History

`enrich.failures.jsonl` should be append-only across resumes:

- every failed attempt appends a row
- later success does not remove earlier failure rows
- resume does not truncate or reconcile away old failures

This file becomes an audit trail, not an unresolved-only ledger.

## Options Considered

### Option 1: Immediate canonical flush on success

Pros:

- simplest operator model
- strongest durability
- no hidden in-memory success backlog
- fixes the live issue directly

Cons:

- canonical output order becomes completion order

### Option 2: Keep ordered canonical files and add a raw-success ledger

Pros:

- preserves ordered canonical files

Cons:

- adds another artifact operators must reason about
- still defers canonical rows
- does not match the requested behavior

## Recommendation

Use Option 1.

For realtime per-word enrich, durability and resume safety matter more than maintaining lexeme-sorted artifact order. The canonical files should advance immediately on each success.

## Implementation Shape

1. Remove the ordered-flush dependency for successful outcomes in per-word mode.
2. Append completed lexeme rows immediately when a word job returns successfully.
3. Keep `completed_lexeme_ids` updated from checkpoint appends so resume and `max_new_completed_lexemes` remain correct.
4. Stop reconciling `enrich.failures.jsonl` on resume and on later success.
5. Keep `enrich.failures.jsonl` append-only.

## Test Requirements

Add failing tests first for:

1. success after a prior failure is flushed immediately to checkpoint/decisions/output before process exit
2. `--resume` preserves prior failure rows and appends a later failure attempt instead of truncating history
3. a lexeme that previously failed but later succeeds is skipped on subsequent resume because checkpoint now contains it

## Operator Impact

- `enrich.checkpoint.jsonl`, `enrich.decisions.jsonl`, and `words.enriched.jsonl` should now keep growing during active runs even after earlier failures
- `enrich.failures.jsonl` becomes append-only historical evidence
- operators should rely on checkpoint for “already done” semantics, not failures
