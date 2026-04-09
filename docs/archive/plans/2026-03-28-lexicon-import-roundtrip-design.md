# Lexicon Import Round-Trip Hardening Design

## Goal

Make `import-db` reliable and observable for large lexicon fixtures, complete a real `full` fixture import->export->compare audit, and document exactly which compiled JSONL fields are preserved, normalized, or dropped by the database round-trip.

## Problems to solve

1. `import-db` on `tests/fixtures/lexicon-db/full/approved.jsonl` is too slow to complete practically on the current path.
2. The current importer still behaves like a row-by-row ORM hydration pipeline with repeated reads and flush pressure on parent/child inserts.
3. We have verified translation round-trip on `smoke`, but not on `full`.
4. We have answered schema-parity questions manually, but we do not have a repeatable regression harness that proves which fields survive round-trip and where normalization is expected.
5. The admin/perf discussion needs a defensible answer grounded in actual import/export behavior at large scale.

## Recommended approach

### 1. Keep the import contract stable

Do not change the compiled JSONL schema in this slice. The importer and exporter should still accept and emit the current compiled row contract.

### 2. Optimize importer execution without changing semantics

Improve throughput by changing how the importer works internally:
- process rows in bounded chunks
- preload existing word/phrase/reference rows for each chunk
- stream JSONL rows into chunk lists instead of materializing the full file up front
- avoid guaranteed-miss reads for newly created parents/children
- reduce flush pressure safely by building child objects from live parent relationships where possible instead of forcing ID acquisition early

The key rule is that this must remain semantically equivalent to the current importer.

### 3. Add a repeatable round-trip audit harness

Add a lexicon test/helper path that can:
- import a fixture into a fresh DB
- export it back out
- compare source vs exported rows by:
  - entry identity
  - top-level keys
  - nested translation structures
  - selected normalized fields such as forms

This audit must distinguish:
- exact preservation
- acceptable normalization
- unexpected loss

### 4. Make field preservation explicit

Document the import/export parity in a machine-readable or at least testable structure:
- fully preserved
- normalized but not lost
- not preserved in first-class DB storage

That gives a concrete answer to whether the DB contains all original JSONL fields.

### 5. Re-verify admin-scale implications

The admin compiled-review/export changes already moved bulk actions to async jobs and paginated loading. After importer optimization, re-run the relevant backend/admin/E2E slices to ensure the admin tool still behaves correctly under large-data assumptions.

## Alternatives considered

### A. Only add more chunk commits

Rejected.
This improves failure boundaries but does not address the row-by-row ORM/query pattern that is causing the `full` fixture bottleneck.

### B. Replace import with raw SQL / COPY in this slice

Rejected.
That would be faster, but it is a much larger semantic rewrite and would create high risk around the existing domain relationships and tests.

### C. Skip the `full` audit and rely on `smoke`

Rejected.
The user explicitly asked whether the real data survives import/export, especially translations. `smoke` is useful, but it is not enough to answer the production-shaped question.

## Expected outcomes

1. `import-db` completes the `full` fixture in a practical amount of time on a fresh DB.
2. We have a verified `full` fixture import->export->compare result.
3. We can state exactly whether translations survive round-trip and where normalization occurs.
4. We have regression coverage so future importer/exporter changes cannot silently drop key fields.

## Files expected to change

- `tools/lexicon/import_db.py`
- `tools/lexicon/export_db.py` if parity helpers need exporter normalization visibility
- `tools/lexicon/tests/test_import_db.py`
- `tools/lexicon/tests/test_cli.py` or a new round-trip test module
- `docs/status/project-status.md`
- potentially a new plan/audit doc if the field matrix needs a durable home

## Verification targets

- targeted lexicon importer/exporter tests
- fresh `full` fixture import timing/progress evidence on a clean DB
- `smoke` and `full` round-trip comparison outputs
- relevant admin/backend regression checks if touched by the slice
