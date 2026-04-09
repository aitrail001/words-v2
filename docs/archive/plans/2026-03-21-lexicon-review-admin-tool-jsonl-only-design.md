# Lexicon Review Admin Tool JSONL-Only Design

Date: 2026-03-21
Status: Design only

## Decision Context

The implemented compiled-review admin tool stages review state in dedicated database tables and exports JSONL overlays afterward.

This document records the lighter alternative: keep compiled artifacts and review decisions entirely file-based, with no review-state persistence in the backend database.

## Goal

Support operator review of compiled learner-facing JSONL artifacts before final `import-db`, while keeping the review layer artifact-native and avoiding review-table schema/migration work.

## Proposed Flow

1. Operator selects a compiled JSONL artifact.
2. UI reads the artifact directly from disk or through a file-serving backend endpoint.
3. UI renders rows, filters, and detail views from the parsed JSONL payload.
4. Review actions write decision rows to a sidecar JSONL file, not to DB tables.
5. `review-materialize` converts:
   - compiled artifact JSONL
   - decisions sidecar JSONL
   into:
   - approved JSONL
   - rejected overlay JSONL
   - regenerate JSONL
6. Only the approved JSONL moves into `import-db`.

## Data Model

### Artifact inputs

- `words.enriched.jsonl`
- `phrases.enriched.jsonl`
- `references.enriched.jsonl`

### Review sidecars

- `review.decisions.jsonl`
- optional `review.session.json` for UI-local state such as cursor, filters, or reviewer notes

### Export outputs

- `approved.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`

## UI Shape

The UI can still live in `admin-frontend`, but it behaves as a file-backed viewer/editor rather than a DB-backed admin tool.

### Required capabilities

1. Open local or uploaded compiled artifact
2. Parse JSONL server-side
3. Search/filter rows by:
   - `entry_id`
   - `entry_type`
   - `normalized_form`
   - QC/validator issues
4. Inspect the full compiled payload
5. Approve/reject/reopen rows
6. Save decisions back to `review.decisions.jsonl`
7. Export materialized outputs via `review-materialize`

## Backend Requirements

Minimal backend support only:

1. File upload or path selection endpoint
2. Artifact parsing endpoint
3. Decision sidecar write endpoint
4. Materialize/export endpoint

No review ORM tables, no review migrations, and no review-state query API would be required.

## Pros

1. Simpler operational model
2. No review-staging schema or migration
3. Closer to the artifact-first lexicon workflow
4. Easier local/offline single-operator use
5. Lower implementation and maintenance cost

## Cons

1. Weak multi-user collaboration
2. Harder concurrency guarantees around decision writes
3. Weaker audit/history model unless sidecar append rules are made strict
4. Harder to recover partial review state across sessions cleanly
5. Server-side filtering/search/pagination must be custom over files instead of SQL-backed

## Performance Expectation

This should be feasible and reasonably fast for typical lexicon artifact sizes if:

1. JSONL parsing happens server-side
2. The UI uses pagination or virtualization
3. Large files are indexed once per session instead of reparsed on every interaction

The main risk is not raw performance. The main risk is operational complexity once multiple reviewers or stronger audit guarantees are needed.

## Recommended Use Case

Use the JSONL-only design if:

1. Review is mainly single-operator
2. Durability and audit needs are modest
3. The priority is minimal infrastructure

Keep the implemented DB-backed review if:

1. Multiple admins need to review
2. Review history matters
3. Queueing, auditability, and persistent status matter more than architectural simplicity

## Relationship To Current Implementation

This is an alternative design, not a replacement for the current branch.

The current branch keeps:

1. JSONL artifact input
2. DB-backed review state
3. JSONL exports

This document exists so the lighter path remains available if the team later decides the current review staging model is heavier than needed.
