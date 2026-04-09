# ADR-004: Lexicon Canonical Final Ingestion Path

**Status:** AMENDED  
**Date:** 2026-03-08  
**Updated:** 2026-04-08

## Context

This ADR originally described the lexicon final-ingestion path while the tool still used older staged-review and `compile-export` assumptions.

The current lexicon operator contract has changed.

## Current decision

The current canonical final learner-data path is:

1. `build-base`
2. optional phrase inventory / form-adjudication steps
3. `enrich`
4. `validate`
5. human review of `words.enriched.jsonl`
6. `import-db` from reviewed `approved.jsonl`
7. optional voice generation / voice import from reviewed rows

Batch workflows may still use intermediate ledgers, but accepted rows materialize into the same learner-facing `words.enriched.jsonl` contract before review.

## No longer current

The active pipeline no longer treats these as supported operator-surface requirements:

- `compile-export` as the canonical final step
- legacy `senses.jsonl` / `concepts.jsonl` / staged-selection review flows as the main current path

## Source of truth

For the live operator contract, use `tools/lexicon/README.md`.

## Consequences

Positive:
- one current learner-facing contract feeds review and import
- operator docs can focus on the real path in use now
- review happens against the actual compiled learner-facing rows

Negative:
- older docs and tools that mention `compile-export` as canonical must be archived or relabeled
