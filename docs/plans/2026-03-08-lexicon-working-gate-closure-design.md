# Lexicon Working-Gate Closure Design

## Goal

Close the lexicon tool as a **working local-DB admin tool** by finishing three final slices:

1. Canonicalize the final ingestion path.
2. Record one clean end-to-end DB smoke.
3. Freeze the operator working-gate checklist.

This is explicitly a **working-tool closure** target, not a full production-hardening target.

## Canonical final ingestion path

The canonical final DB write path for generated lexicon data is:

1. `build-base`
2. optional `score-selection-risk` / `prepare-review`
3. `enrich`
4. `validate --snapshot-dir`
5. `compile-export`
6. `validate --compiled-input`
7. `import-db`

### What staged review is for

The staged review backend remains the review/inspection/control layer for sense selection decisions.

It is **not** the canonical final learner-enrichment publisher.

Why:
- `import-db` now owns the richer learner-facing DB writeback (`meaning_examples`, `word_relations`, enrichment jobs/runs, phonetic provenance).
- staged review publish was built first around a smaller current-schema publish projection.
- having both paths act as equal final publishers would create drift and operator ambiguity.

### Practical rule

- use staged review to decide what should be imported
- use `compile-export -> import-db` to land learner-facing content into the local DB

## Working gate vs future hardening

### Working Gate v1

The tool is considered working when:
- the canonical path is documented
- one clean end-to-end DB smoke is recorded
- operator pass/fail checklist exists
- remaining gaps are documented as future TODOs, not left ambiguous

### Explicitly deferred beyond closure

- admin frontend review UI
- stronger RBAC/admin-only authorization
- phrase/idiom and phrase-linking expansion
- richer learner-facing public API projection
- batch reliability controls and budget/rate governance
- automated live Postgres import smoke in CI
- stricter compiled validation and review-status gating before import

## Smoke definition

A closure smoke should prove all of these in one clean environment:
- build snapshot records
- enrich snapshot records
- validate snapshot files
- compile learner export
- validate compiled export
- import into clean local DB
- read back imported learner-facing enrichment through backend API

## Success criteria

This closure slice is complete when:
1. docs clearly name one canonical final ingestion path
2. status board records one clean end-to-end DB smoke with evidence
3. a reusable operator working-gate checklist exists
4. deferred improvements are explicitly documented as TODOs
