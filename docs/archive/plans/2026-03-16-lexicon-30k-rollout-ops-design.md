# Lexicon 30K Rollout Operations Design

Date: 2026-03-16
Owner: Codex

## Goal

Run the curated deterministic 30K lexicon snapshot through the real LLM enrichment pipeline in this session while keeping the snapshot artifacts in `data/lexicon/snapshots/...`, periodically projecting the current compiled output into the local DB so the result can be inspected in the app and admin surfaces during the long-running rollout.

## Context

The curated deterministic 30K base snapshot already exists at:

- `data/lexicon/snapshots/words-30000-20260314-main-real-entity-tail-hardened`

It contains:

- `30000` lexemes
- `63126` senses
- `56507` concepts
- `0` unresolved ambiguous-form rows

The enrichment path is already benchmarked and the current recommendation is:

- one word per request only
- `gpt-5-nano` in `word_only` mode as the default
- `gpt-5.1` in `word_only` mode as the fallback

Grouped batching was explicitly tested and rejected as a rollout method.

## Requirements

The 30K rollout needs to satisfy all of these at once:

1. Preserve durable artifact truth under `data/lexicon/snapshots/...`
2. Keep the run resumable through checkpoint and failure sidecars
3. Avoid holding the entire output in memory until the end
4. Allow local DB inspection during the run
5. Avoid turning the DB into the only source of truth
6. Keep operator behavior simple enough to run and monitor safely from one long-lived session

## Chosen Approach

Use one continuously resumable snapshot directory for the live 30K run, and treat the database as a refreshable inspection projection of the current compiled artifact state.

This means:

- the live enrichment run appends to one snapshot directory
- completed lexemes are flushed incrementally to `enrichments.jsonl`
- progress is tracked in `enrich.checkpoint.jsonl`
- failures are tracked in `enrich.failures.jsonl`
- periodic milestone passes rerun `compile-export`, `validate --compiled-input`, and `import-db`
- the canonical retained output remains the files in `data/lexicon/snapshots/...`

## Why One Snapshot Directory

This is the best fit for the current tool behavior.

Benefits:

- resume behavior stays simple
- checkpoint and failure ledgers stay in one place
- compiled exports are always derived from the same evolving snapshot
- import provenance remains straightforward
- final validation is simpler than stitching multiple chunk directories together

Rejected alternative:

- separate per-chunk snapshot directories

Reason rejected:

- adds consolidation complexity
- creates more opportunities for operator error
- does not materially improve durability over the current checkpointed single-snapshot model

## Chunking Strategy

Use milestone-based operator chunks, not separate snapshot partitions.

Recommended cadence:

- first live milestone: `250` words
- steady-state milestone after the smoke passes: `500` words

Rationale:

- `250` is small enough to validate the real production path safely
- `500` is large enough to make DB preview imports worthwhile
- both are small enough that failures remain inspectable and recovery remains manageable

## Preview Import Model

DB preview imports should happen at milestone boundaries, not continuously after each lexeme.

After each milestone:

1. inspect checkpoint progress
2. inspect any new failure rows
3. rerun `compile-export`
4. rerun `validate --compiled-input`
5. rerun `import-db`
6. inspect the imported result through the app/admin surfaces as needed

This makes the DB a refreshable local mirror of current compiled artifact state without weakening the file-based durability guarantees.

## Failure Policy

The live run should continue only while these conditions remain true:

- checkpoint growth is monotonic
- enrichments are still flushing to disk
- failure count stays within a bounded threshold for the current milestone
- validation of the compiled export remains clean

The live run should pause when any of these happen:

- repeated failures cluster on the same lexemes
- failure volume exceeds the milestone threshold
- compiled validation breaks
- DB import stops reflecting the compiled artifact correctly

Fallback rule:

- use `gpt-5-nano word_only` by default
- use `gpt-5.1 word_only` only as a targeted fallback for stubborn subsets or if the default model shows unacceptable quality/failure behavior

## DB and Runtime Policy

The local DB is for inspection, not for canonical retention.

Rules:

- keep the canonical run under `data/lexicon/snapshots/<run-name>/`
- keep the compiled `words.enriched.jsonl` in the same snapshot directory
- re-import from artifacts instead of patching rows manually in the DB
- refresh the Docker stack only if import or API inspection shows runtime drift

This lets parallel sessions continue working on the admin frontend, learner app, and other lexicon slices without turning this rollout session into an opaque one-off state machine.

## Intended Run Output Layout

The live rollout snapshot should contain at least:

- `lexemes.jsonl`
- `senses.jsonl`
- `concepts.jsonl`
- `ambiguous_forms.jsonl`
- `enrichments.jsonl`
- `enrich.checkpoint.jsonl`
- `enrich.failures.jsonl`
- `words.enriched.jsonl`

Optional monitoring or operator notes can live alongside those files if needed, but the main pipeline should continue using the standard artifact names the tool already understands.

## Expected Operator Workflow

1. Create a new dated 30K run snapshot directory under `data/lexicon/snapshots/`
2. Seed it from the curated deterministic 30K base snapshot
3. Run the first real `250`-word milestone
4. Validate and preview-import that milestone
5. If healthy, continue with repeated `500`-word milestones using `--resume`
6. Periodically inspect the imported results in the local stack
7. Continue until the checkpoint reaches full completion
8. Perform final compile, validate, import, and signoff against the completed artifact set

## Success Criteria

This design is successful if:

1. The live 30K run can be resumed safely after interruption
2. The evolving artifact set remains under `data/lexicon/snapshots/...`
3. Preview imports can be refreshed during the run
4. The final result still comes from `compile-export -> import-db`
5. Operators can inspect progress without depending on the DB as the only retained output
