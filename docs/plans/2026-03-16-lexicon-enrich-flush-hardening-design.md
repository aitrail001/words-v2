# Lexicon Enrich Flush Hardening Design

Date: 2026-03-16
Owner: Codex

## Goal

Remove the misleading "process is active but disk looks stalled" behavior from large per-word lexicon enrichment runs by hardening how completed lexemes are durably written during concurrent execution.

## Observed Behavior

During the live 30K rollout:

- gateway/API traffic continued
- the enrich process stayed alive
- but `enrich.checkpoint.jsonl` and `enrichments.jsonl` sometimes stopped advancing for long periods

This made it look like the run was not flushing to disk even while requests were still in flight.

## Root Cause

The current per-word concurrency path stores completed lexeme results in `completed_results` and only flushes them through `flush_completed()`.

That function advances from `next_flush_index` through the globally ordered lexeme list and stops at the first gap:

- if the next expected lexeme is not ready yet, flush stops
- later completed lexemes remain buffered in memory
- checkpoint growth pauses even if later futures already finished

This means a single slow or stuck earlier lexeme can block durable progress for many later successful lexemes.

## Why This Is A Problem

For long runs, operators care about:

- durable progress
- visible progress
- resumability after interruption

The current behavior hurts all three:

- later successes may sit only in memory
- apparent progress can flatline even while work is still happening
- interrupting the run during a blocked gap risks losing buffered later completions that were never flushed

## Design Objective

Preserve deterministic operator visibility and resumability without requiring global ordered flush to advance first.

## Options Considered

### Option 1: Flush completed lexemes immediately to the canonical files, regardless of order

Pros:

- strongest durability
- simplest operator model
- no hidden in-memory backlog

Cons:

- output file order becomes completion order, not lexeme order
- tests and some operator assumptions may currently expect ordered output

### Option 2: Keep canonical ordered files, but add an append-only raw-completions ledger

Pros:

- preserves ordered canonical files
- adds immediate durable evidence of success
- easiest migration path with lower compatibility risk

Cons:

- introduces dual progress sources
- resume logic must reconcile the new ledger correctly

### Option 3: Keep current ordering but add stronger timeout/cancellation of blocking futures

Pros:

- minimal change to artifact shape

Cons:

- still ties durability to ordered advancement
- does not solve the hidden-progress problem when latency is high but not timed out

## Recommendation

Use Option 2 first.

Add an immediate append-only per-lexeme completion ledger that writes as soon as a lexeme finishes successfully, independent of the global flush order, while keeping the current ordered canonical files for compatibility.

This gives:

- immediate durable evidence of success
- better operator observability
- safer interruption/restart behavior
- lower compatibility risk than immediately changing canonical output ordering

## Proposed Artifact Model

Keep existing files:

- `enrichments.jsonl`
- `enrich.checkpoint.jsonl`
- `enrich.failures.jsonl`

Add a new append-only success ledger, for example:

- `enrich.completed.raw.jsonl`

Each row should include:

- `lexeme_id`
- `lemma`
- `generation_run_id`
- `completed_at`
- the completed enrichment payload rows for that lexeme, or enough data to reconstruct them safely

## Resume Semantics

On resume:

- canonical checkpoint remains the source of truth for already checkpointed completions
- raw completion ledger is used to recover any successfully completed-but-not-yet-canonicalized lexemes from the previous interrupted run
- failures ledger remains only the active unresolved failure list

This closes the current durability gap where completed futures can exist only in memory behind an ordered flush barrier.

## Minimal Hardening Slice

1. Add tests reproducing the blocked-gap case:
   - earlier lexeme hangs or is delayed
   - later lexeme completes
   - raw completion ledger must still flush immediately
2. Add the raw completion ledger write path
3. Add resume reconciliation from raw completion ledger into canonical checkpoint/output
4. Preserve current ordered canonical output for now
5. Update operator docs to explain:
   - canonical ordered files
   - raw completion ledger
   - active failures ledger

## Follow-Up Hardening

If the raw-completion ledger proves stable, a later follow-up can consider changing canonical output ordering entirely or adding explicit worker/future timeout controls.
