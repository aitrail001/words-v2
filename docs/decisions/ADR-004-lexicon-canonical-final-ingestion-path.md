# ADR-004: Lexicon Canonical Final Ingestion Path

- Date: 2026-03-08
- Status: Accepted

## Context

The lexicon project now has two adjacent flows:

1. staged review/publish backend for reviewing sense-selection decisions
2. offline `compile-export -> import-db` flow for importing learner-facing enriched lexicon data into the local DB

The richer learner-facing writeback now lives in `import-db`, including examples, relations, enrichment jobs/runs, and phonetic provenance.

Without a clear decision, operators could treat both paths as equivalent final publishers, leading to ambiguity and drift.

## Decision

The canonical final DB write path for generated lexicon content is:

- `build-base`
- optional staged review preparation
- `enrich`
- `validate --snapshot-dir`
- `compile-export`
- `validate --compiled-input`
- `import-db`

Staged review remains the selection/review control layer, not the canonical final learner-enrichment publisher.

## Consequences

### Positive
- one clear operator path into the local DB
- richer learner-facing writeback stays centralized in one importer
- staged review can evolve independently as review/control infrastructure

### Negative
- staged review publish remains a narrower legacy/current-schema projection until later unification
- future work may still unify staged review publish with importer semantics, but that is not required for the working-gate closure

## Deferred follow-up

Possible future improvement:
- make staged review publish delegate to the same importer/writeback path instead of maintaining a smaller direct publish projection
