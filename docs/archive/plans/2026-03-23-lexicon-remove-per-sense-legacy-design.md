# Lexicon Remove Per-Sense Legacy Design

Date: 2026-03-23
Owner: Codex

## Goal

Remove the remaining legacy `per_sense` enrichment mode and its `enrichments.jsonl`-based artifact path from the active lexicon toolchain.

## Current Problem

The repo status and operator workflow already describe the lexicon tool as per-word and compiled-artifact-first, but the codebase still exposes legacy `per_sense` behavior in several places:

- `lexicon enrich --mode per_sense`
- runtime branching in `tools/lexicon/enrich.py`
- legacy realtime output naming around `enrichments.jsonl`
- compile/validate/canonical-registry readers that still understand the old artifact
- tests that continue to preserve or exercise the sense-era path

This is policy drift. It keeps dead code alive and implies support for an operator path we no longer want to carry.

## Required Outcome

### CLI

`enrich` should be per-word only.

- remove `per_sense` from the CLI surface
- remove `--mode per_sense`
- update help strings to describe only `words.enriched.jsonl` and the per-word sidecars

### Runtime

Remove the per-sense branch from realtime enrichment.

- delete legacy mode constants/defaults
- delete the per-sense execution branch
- keep only the per-word compile/checkpoint/decision/failure behavior

### Downstream Artifacts

Remove active-tool support for `enrichments.jsonl` where that support exists only for the removed mode.

That includes:

- compile/export paths
- validate snapshot behavior
- canonical registry status lookup where relevant

Historical snapshots that only contain `enrichments.jsonl` will no longer be supported by the active toolchain.

## Options Considered

### Option 1: Full removal now

Pros:

- matches the desired supported workflow
- removes policy drift cleanly
- lowers maintenance cost

Cons:

- historical sense-era snapshots lose active-tool compatibility

### Option 2: Hide CLI mode but keep legacy readers

Pros:

- lower short-term risk for old artifacts

Cons:

- leaves dead code and ambiguous support boundaries

### Option 3: Auto-migrate old snapshots

Pros:

- historical compatibility preserved

Cons:

- adds migration behavior for a path we want gone
- more complexity than the remaining value justifies

## Recommendation

Use Option 1.

The repo already treats the sense-era path as legacy. We should make the code match the declared contract.

## Testing Requirements

Add failing tests first for:

1. CLI no longer accepting `--mode per_sense`
2. runtime no longer exposing a per-sense execution branch
3. snapshot validation/registry no longer treating `enrichments.jsonl` as the active realtime artifact
4. any existing tests expecting ordered legacy outputs are either removed or rewritten to the per-word contract

## Documentation Impact

Update:

- operator guide
- project status
- any CLI/help tests still referring to `per_sense` or `enrichments.jsonl` as an active path
