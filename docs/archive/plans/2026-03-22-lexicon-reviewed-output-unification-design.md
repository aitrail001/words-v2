# Lexicon Reviewed Output Unification Design

## Goal

Unify `Compiled Review`, `JSONL Review`, `Lexicon Ops`, and `Import DB` around one reviewed-artifact contract so operators do not have to reason about different output locations or capabilities by review mode.

## Problem

The current admin flow mixes two incompatible mental models:

- `Compiled Review` can download reviewed outputs, but does not materialize them into the snapshot directory
- `JSONL Review` can materialize reviewed outputs into the snapshot directory, but does not expose matching download actions
- `Lexicon Ops` and `Import DB` already prefer `approved.jsonl`, but reviewed outputs still live inconsistently between browser downloads and on-disk artifacts

This creates three operator problems:

1. reviewed outputs are not discoverable from one stable location
2. downstream pages cannot assume a single reviewed-artifact contract
3. the same conceptual outputs appear differently depending on which review mode was used

## Decision

Adopt a shared reviewed-output directory under each snapshot:

`data/lexicon/snapshots/<snapshot>/reviewed/`

All review modes should converge on the same four reviewed outputs:

- `approved.jsonl`
- `review.decisions.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`

## Layout

Snapshot root remains the home for pre-review artifacts:

- `words.enriched.jsonl`
- `phrases.enriched.jsonl`
- `references.enriched.jsonl`
- review-prep sidecars such as `*.review_qc.jsonl`

Reviewed outputs move under `reviewed/`:

- `reviewed/approved.jsonl`
- `reviewed/review.decisions.jsonl`
- `reviewed/rejected.jsonl`
- `reviewed/regenerate.jsonl`

## Behavior

### Compiled Review

- keep download actions
- add a materialize action that writes the four reviewed outputs into the shared `reviewed/` directory
- default the output directory to the selected snapshot’s `reviewed/` path when known

### JSONL Review

- keep materialize action
- add download actions for the same four outputs
- default the output directory to the snapshot’s `reviewed/` path when launched from `Lexicon Ops`

### Lexicon Ops

- check compiled artifacts in the snapshot root
- check reviewed outputs under `reviewed/`
- treat `reviewed/approved.jsonl` as the canonical import-ready signal

### Import DB

- default to `reviewed/approved.jsonl`
- keep manual override capability for advanced operators

## Why one shared folder

Do not create separate output folders per review mode.

Bad alternatives:

- `compiled-review/approved.jsonl`
- `jsonl-review/approved.jsonl`

That would force `Lexicon Ops` and `Import DB` to know how review happened. They should only care whether reviewed outputs exist.

One shared `reviewed/` folder keeps the artifact contract stable regardless of the review mode.

## Backend/API implications

### Compiled Review

Add a materialize endpoint that:

- derives the four reviewed outputs from the DB-backed batch state
- writes them into a requested or default output directory
- returns the output paths and counts

### JSONL Review

Add export/download endpoints for:

- approved
- decisions
- rejected
- regenerate

These should use the same normalized reviewed-output contract as materialization.

## Testing impact

Required:

- frontend tests for both pages exposing both download and materialize affordances
- backend tests for compiled-review materialization into `reviewed/`
- `Lexicon Ops` tests updated to look under `reviewed/`
- `Import DB` tests updated to prefer `reviewed/approved.jsonl`
- focused Playwright smoke covering the new reviewed directory behavior

