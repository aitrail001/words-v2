# Status: DRAFT
# Lexicon Review Admin Tool Implementation Plan

Date: 2026-03-21  
Owner: Lexicon/Admin tooling  
Scope: `tools/lexicon`, `backend`, `admin-frontend`, `e2e`, `docs`

## 1. Objective

Implement a production-grade admin review tool for compiled lexicon JSONL artifacts so operators can approve or reject generated entries before DB import, and export deterministic regeneration requests for rejected entries.

## 2. Delivery strategy

Implement this in controlled stages so the existing lexicon pipeline remains stable.

### Hard constraints

- Do not break current `build-base`, `enrich`, `validate`, `compile-export`, or `import-db` behavior.
- Keep generated lexicon artifacts immutable.
- Use the current final importer (`import-db`) as the v1 publisher.
- Follow repo docs conventions under `docs/plans/`.

## 3. Stage plan

## Stage 0 — Repo mapping and ADR-level validation

### Goals

- confirm actual backend router/model layout
- confirm actual admin-frontend route/component layout
- confirm migration workflow and auth pattern for admin routes
- document exact code locations before writing feature code

### Tasks

- inspect backend application structure
- inspect admin-frontend structure
- identify migration tooling and conventions
- identify existing auth/admin guard patterns
- identify where lexicon schema models currently live in backend

### Deliverables

- updated design notes inline in plan PR if needed
- implementation checklist mapped to real repo paths

### Acceptance criteria

- all feature locations are mapped to real repo paths
- no speculative routing/module layout remains unresolved

## Stage 1 — Review DB schema and backend domain model

### Goals

Add durable review storage.

### Tasks

- create migration for:
  - `lexicon_review_batches`
  - `lexicon_review_items`
  - `lexicon_review_item_events`
  - `lexicon_regeneration_requests`
- add ORM models
- add query helpers / repositories / service interfaces
- add seed/test fixtures

### Acceptance criteria

- migrations apply cleanly up and down
- indexes/uniques match design
- test DB can create/read/update review batch and item state

### Tests

- migration smoke test
- ORM create/load/update test
- uniqueness test for `(batch_id, entry_id)`
- audit-event append test

## Stage 2 — Backend ingest and export services

### Goals

Implement batch ingest and deterministic export.

### Tasks

- add compiled JSONL ingest service
- validate artifact hash and row uniqueness during ingest
- derive `search_text`, metadata fields, and initial counts
- add export service for:
  - `review.decisions.jsonl`
  - `approved.jsonl`
  - `rejected.jsonl`
  - `regenerate.jsonl`
- add batch stats service

### Acceptance criteria

- compiled artifact can be ingested as a review batch
- counts are correct for pending items
- exports are deterministic and stable
- exported `approved.jsonl` preserves original compiled payload

### Tests

- ingest compiled words fixture
- ingest compiled phrases fixture
- duplicate `entry_id` rejection test
- export approved/rejected/regenerate golden-file tests
- artifact hash mismatch test

## Stage 3 — Backend admin API

### Goals

Expose review workflows to the admin UI.

### Tasks

- add admin routes for:
  - batch create/list/detail
  - items list/detail
  - approve/reject/reopen
  - export endpoints
  - stats endpoint
- enforce admin-only access
- add response schemas
- add pagination/filter support

### Acceptance criteria

- authenticated admin can manage a batch end to end
- non-admin access is rejected
- filters and pagination work for large batches

### Tests

- API unit/integration tests for each endpoint
- auth/permission tests
- validation tests for bad decision transitions
- export endpoint tests

## Stage 4 — `tools/lexicon` materialization bridge

### Goals

Add a CLI-safe offline bridge between review decisions and import/regeneration artifacts.

### Tasks

- add `review-materialize` command in `tools/lexicon/cli.py`
- add `review_materialize.py`
- validate decision file against compiled input
- emit:
  - approved output
  - rejected output
  - regenerate output
- fail loudly on:
  - duplicate decisions
  - unknown `entry_id`
  - mixed artifact hashes
  - invalid decision values

### Acceptance criteria

- operator can materialize approved/rejected/regenerate artifacts offline
- existing `import-db` works on approved output with no codepath regression

### Tests

- happy path golden-file test
- missing decision test
- duplicate decision test
- unknown `entry_id` test
- invalid artifact hash test

## Stage 5 — Admin frontend review UX

### Goals

Build the operator UI.

### Tasks

- add review batch list page
- add review queue/detail view
- add filters and search
- add approve/reject/reopen actions
- add keyboard shortcuts
- add export buttons
- show validator/QC issues when present

### Acceptance criteria

- reviewer can complete a batch without touching raw JSONL
- status counts update live after actions
- detail panel shows all learner-facing content needed for judgment

### Frontend tests

- batch list render test
- item detail render test
- approve flow test
- reject flow test
- filter/search test
- keyboard shortcut test

## Stage 6 — End-to-end review/import/regenerate flow

### Goals

Prove the whole operator workflow.

### Tasks

- add end-to-end scenario:
  - ingest compiled fixture
  - approve some rows
  - reject some rows
  - export approved/regenerate artifacts
  - run `import-db` on approved output in test environment
- verify rejected rows never enter DB
- verify regenerate output contains rejected rows only

### Acceptance criteria

- end-to-end scenario passes in CI
- import counts match approved decisions exactly

### E2E tests

- words-only batch
- mixed entity-category batch
- phrases batch
- reference entries batch (if already implemented in repo)

## Stage 7 — Operator docs and rollout hardening

### Goals

Make the feature operable by humans and safe for real datasets.

### Tasks

- add/update runbook docs
- add screenshots or workflow notes if appropriate
- document recommended batch sizes for human review
- document recovery steps for partial review/export failures
- document promotion flow from reviewed artifact to DB import

### Acceptance criteria

- a new operator can run the workflow from docs alone
- rollback/recovery steps are documented

## 4. File-level implementation targets

Exact paths should follow the repo’s real structure discovered in Stage 0. The targets below are the intended responsibility boundaries.

### `tools/lexicon`

Add/modify:

- `tools/lexicon/cli.py`
- `tools/lexicon/review_materialize.py`
- `tools/lexicon/tests/test_review_materialize.py`
- optional `tools/lexicon/tests/fixtures/review/*.jsonl`

### `backend`

Add/modify:

- review DB models
- migration files
- review service layer
- admin review router(s)
- API schemas
- backend tests

### `admin-frontend`

Add/modify:

- route(s) for review batches and review queue
- data-fetching hooks/service client
- batch table component
- review detail component
- decision actions and export actions
- unit/component tests

### `e2e`

Add/modify:

- end-to-end review flow specs

### `docs`

Add/modify:

- runbook / rollout docs
- plan updates if the real structure differs from assumptions

## 5. Mocking strategy

## Backend/API mocking

- Use fixture compiled JSONL files for ingest tests.
- Mock file storage/download layer if export uses file storage.
- Use test DB transactions or disposable DB instances for API tests.

## Frontend mocking

- Mock admin review API responses in unit/component tests.
- Use realistic batch/item payload fixtures.

## CLI mocking

- Use local JSONL fixtures only.
- No network calls.
- No dependence on live backend in unit tests.

## E2E environment

- Run against local test backend + test DB.
- Use deterministic fixture artifacts.

## 6. Safety checks

### Preserve existing behavior

Before merging, prove:

- `build-base` unchanged
- `enrich` unchanged
- `validate` unchanged
- `compile-export` unchanged unless intentionally extended
- `import-db` unchanged for existing inputs

### Required regression suite

- existing lexicon CLI tests pass
- existing backend API tests pass
- existing admin-frontend tests pass
- new review tool tests pass

## 7. Definition of done

The feature is done when all of the following are true:

1. A compiled lexicon JSONL file can be ingested into a review batch.
2. Admin reviewers can approve and reject entries in the UI.
3. Review actions are audited.
4. Approved and rejected artifacts can be exported deterministically.
5. `regenerate.jsonl` can be exported for rejected entries.
6. `import-db --input approved.jsonl` imports only approved rows.
7. Rejected rows are excluded from import in automated tests.
8. E2E review flow passes in CI.
9. Operator docs are present.
10. No existing lexicon flow regresses.

## 8. Recommended implementation order inside Codex

1. Stage 0 repo mapping
2. Stage 1 DB schema
3. Stage 2 ingest/export services
4. Stage 3 API
5. Stage 4 CLI materialization bridge
6. Stage 5 admin frontend
7. Stage 6 E2E verification
8. Stage 7 docs and cleanup

## 9. Nice-to-have follow-ons after v1

- inline override editing
- reviewer assignment workflow
- side-by-side diff against currently published DB entry
- bulk actions
- one-click import of approved batch from admin UI
- direct regenerate action that submits a new lexicon job
