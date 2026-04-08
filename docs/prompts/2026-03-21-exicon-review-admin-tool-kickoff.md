# Build the Lexicon Review Admin Tool

Use the configured subagents to implement a production-grade admin review tool for learner-facing lexicon JSONL artifacts in this repository.

## Mission

Implement an admin review tool that lets human reviewers inspect compiled lexicon entries and mark them as:

- approved -> eligible for import
- rejected -> excluded from import and exported for regeneration

The tool must support compiled lexicon artifacts for:

- words
- phrases / idioms / phrasal verbs
- lightweight learner reference entries if they already exist in the repo

## Critical repo constraints

1. Do not break the current lexicon pipeline.
2. Keep generated JSONL artifacts immutable.
3. Keep `import-db` as the v1 final publisher.
4. Use the approved export as the v1 import input.
5. Follow repo docs conventions under `docs/plans/`.
6. Adapt to the real backend and admin-frontend structure you discover in the repo; do not force speculative paths if the repo already has a clear convention.

## Current repo facts you must respect

- The repo already contains `admin-frontend`, `backend`, `tools/lexicon`, `data/lexicon`, `docs`, and `e2e`.
- `tools/lexicon` already supports pre-enrichment review-prep via `score-selection-risk`, `prepare-review`, and `review_queue.jsonl`.
- `compile-export` already materializes learner-facing compiled JSONL.
- `import-db` already imports compiled learner JSONL into lexicon-owned DB tables.
- `compile-export` already supports a decision-layer filter for deterministic-safe selection decisions, so adding a post-enrichment decision layer should follow the same philosophy.

## Required reading before coding

Read and use:

- `docs/plans/2026-03-21-lexicon-review-admin-tool-design.md`
- `docs/plans/2026-03-21-lexicon-review-admin-tool-implementation-plan.md`
- current `tools/lexicon/README.md`
- current `tools/lexicon/cli.py`
- current `tools/lexicon/compile_export.py`
- current `tools/lexicon/import_db.py`
- current backend DB model/migration patterns
- current admin-frontend route/component patterns

## Required subagent usage

Spawn and use the configured subagents where available.

### 1. `repo_analyst`
Task:
- map the actual backend, admin-frontend, migration, auth, and test structure
- produce a short implementation map with exact real paths

### 2. `design_planner`
Task:
- reconcile the design/implementation plan with the real repo structure
- identify any necessary design adjustments before code changes begin

### 3. `schema_validation_engineer`
Task:
- implement or review backend schemas/models/validators for review batches/items/events/regen requests
- review JSONL materialization validation rules

### 4. `test_engineer`
Task:
- build fixture strategy
- add backend, CLI, frontend, and E2E tests
- ensure all tests are deterministic and offline where possible

### 5. `qc_review_engineer`
Task:
- ensure review item metadata cleanly surfaces validator/QC issues in a reviewer-friendly way
- review reject/regenerate export semantics

### 6. `reviewer`
Task:
- perform final code review for correctness, safety, UX completeness, and regression risk

If any configured subagent is missing, do that work yourself and continue.

## Deliverables

### A. Backend review system

Implement:

- review batch persistence
- review item persistence
- immutable review event audit trail
- regeneration request persistence
- admin API endpoints for batch ingest/list/detail, item list/detail, approve/reject/reopen, stats, and artifact export

### B. Admin frontend UI

Implement:

- batch list page
- review queue page
- entry detail panel/page
- approve/reject/reopen actions
- filter/search/sort
- export actions
- keyboard shortcuts if practical

### C. `tools/lexicon` bridge

Implement a v1-safe offline bridge command:

- `review-materialize`

This command must:

- take compiled input JSONL + review decision JSONL
- emit `approved.jsonl`, `rejected.jsonl`, and `regenerate.jsonl`
- fail loudly on invalid decision files, duplicate decisions, unknown entry IDs, and artifact hash mismatches

### D. Tests

Add:

- backend unit/integration tests
- CLI unit/golden tests
- admin-frontend tests
- E2E review/import/regenerate flow test

### E. Docs

Update docs as needed so operators can run the full review workflow.

## Implementation policy

### Preserve existing behavior

You must not regress:

- `build-base`
- `enrich`
- `validate`
- `compile-export`
- `import-db`

### v1 import policy

Do not change the main importer contract first.

Preferred v1 flow:

1. review batch ingest
2. approve/reject in admin UI
3. export `approved.jsonl`
4. run existing `import-db --input approved.jsonl`

### Data policy

- Generated artifacts are immutable.
- Review decisions are stored as an overlay.
- Exported approved/rejected/regenerate files are derived outputs.

### UI policy

Optimize for reviewers handling large queues, not just demo batches.

Required reviewer-facing metadata:

- entry type
- entity category
- frequency rank where available
- CEFR where available
- validator/QC issues where available
- grouped learner-facing content from compiled payload

## Suggested execution order

1. Read repo and map real implementation paths.
2. Compare real structure against the design docs and adjust implementation details if needed.
3. Implement DB schema + models.
4. Implement backend ingest/export services.
5. Implement backend API.
6. Implement `review-materialize` CLI bridge.
7. Implement admin frontend.
8. Add tests.
9. Run the full regression suite.
10. Summarize changes, risks, and any follow-up items.

## Quality gates

Do not stop at partial scaffolding. The feature is only complete when:

- review batches can be ingested
- items can be approved/rejected in the UI
- approved/rejected/regenerate artifacts can be exported
- approved export can be fed to `import-db`
- rejected rows are excluded from import in automated tests
- regression tests pass

## Definition of done

The task is done only when all of the following are true:

1. Production-quality backend review workflow exists.
2. Production-quality admin UI exists.
3. `review-materialize` works and is tested.
4. E2E review -> export -> import path is verified.
5. Existing lexicon flow remains intact.
6. Code is documented, reviewed, and test-backed.

## Output expectations

At the end, provide:

- concise summary of what changed
- exact files added/modified
- migration names
- commands used to run tests
- any remaining follow-up items clearly labeled as non-blocking
