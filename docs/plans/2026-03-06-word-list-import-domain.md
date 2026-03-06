# Word List Import Domain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** COMPLETED  
**Date:** 2026-03-06  
**Goal:** Implement the full word-list import domain (`books`, `word_lists`, `word_list_items`, `import_jobs`) with backend API + progress path, frontend imports wiring, and E2E/CI verification.

**Architecture:** Add new SQLAlchemy domain models and migration while keeping existing `/api/imports` compatibility. Introduce dedicated word-list import APIs (`/api/word-lists/import`, `/api/import-jobs/*`, `/api/word-lists/*`) and a new Celery task that creates `books`, `word_lists`, and `word_list_items` while updating `import_jobs` counters. Expose realtime progress path via SSE endpoint backed by job status snapshots and periodic updates. Wire a new `/imports` frontend page with upload + polling progress UX and protected-route enforcement.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, Redis, Next.js App Router, Jest, Playwright, Docker Compose, GitHub Actions CI.

---

## Design Alignment (Brief)

1. Domain model shape:
- `books` stores deduped source metadata by `content_hash`.
- `word_lists` is user-owned and optionally references a `book`.
- `word_list_items` links canonical `words` into user list scope with per-list frequency/context.
- `import_jobs` is the import execution state machine (`queued -> processing -> completed|failed`).

2. API contract:
- `POST /api/word-lists/import` accepts multipart `.epub` + optional list metadata and returns an import job snapshot.
- `GET /api/import-jobs/{job_id}` returns authoritative progress snapshot.
- `GET /api/import-jobs/{job_id}/events` provides SSE updates until terminal state.
- `GET /api/word-lists`, `GET /api/word-lists/{id}`, `POST /api/word-lists/{id}/items`, `DELETE /api/word-lists/{id}/items/{item_id}`, `DELETE /api/word-lists/{id}` provide list CRUD.

3. Frontend/E2E behavior:
- Add `/imports` protected page for upload + status table + progress.
- Extend auth nav and middleware guards to include `/imports`.
- Add smoke tests for `/imports` guard and import-domain contract; keep tests deterministic and CI-safe.

---

### Task 1: Backend Domain Model + API Contract Tests (RED)

**Files:**
- Create: `backend/tests/test_word_list_models.py`
- Create: `backend/tests/test_word_lists_api.py`
- Create: `backend/tests/test_import_jobs_api.py`

**Step 1: Add failing model tests**
- Assert defaults/relationships for `Book`, `WordList`, `WordListItem`, `ImportJob`.
- Assert unique constraints (`word_list_id + word_id`, `content_hash` uniqueness metadata intent).

**Step 2: Add failing API tests**
- Assert import endpoint validates `.epub` and returns job snapshot.
- Assert import-job snapshot endpoint enforces ownership and 404 semantics.
- Assert SSE endpoint responds with `text/event-stream` and emits current job payload.
- Assert word-list CRUD ownership semantics and item add/remove behaviors.

**Step 3: Run targeted tests to confirm RED**
- Run: `docker compose -f docker-compose.test.yml run --rm --build test pytest backend/tests/test_word_list_models.py backend/tests/test_word_lists_api.py backend/tests/test_import_jobs_api.py -q`
- Expected: failures for missing models/routers/logic.

---

### Task 2: Backend Domain Models + Migration (GREEN)

**Files:**
- Create: `backend/app/models/book.py`
- Create: `backend/app/models/word_list.py`
- Create: `backend/app/models/word_list_item.py`
- Create: `backend/app/models/import_job.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/005_add_word_list_import_domain.py`

**Step 1: Implement model classes + relationships**
- Add explicit FK relationships across `users/books/word_lists/word_list_items/import_jobs`.
- Preserve canonical `words` as dictionary source and connect to list items.

**Step 2: Implement migration**
- Create the four new tables and required indexes/unique constraints.
- Ensure downgrade drops tables in reverse dependency order.

**Step 3: Run focused backend model tests to confirm GREEN**
- Run: `docker compose -f docker-compose.test.yml run --rm --build test pytest backend/tests/test_word_list_models.py -q`

---

### Task 3: Backend Import APIs + Worker + Progress Path (GREEN)

**Files:**
- Create: `backend/app/api/word_lists.py`
- Create: `backend/app/api/import_jobs.py`
- Create: `backend/app/services/import_jobs.py`
- Modify: `backend/app/tasks/epub_processing.py`
- Modify: `backend/app/main.py`

**Step 1: Implement import-job creation + dedupe service**
- Save uploaded epub, hash content, dedupe by user/hash in active/completed states.
- Create queued `ImportJob`, enqueue processing task, handle enqueue failures.

**Step 2: Implement worker domain persistence**
- Parse epub, extract lemmas/frequencies, resolve/create `Book`, create `WordList`, upsert `WordListItem`, update counters, finalize status.

**Step 3: Implement snapshot + SSE progress endpoints**
- Snapshot endpoint returns counters and status.
- SSE endpoint streams initial and incremental updates until terminal state.

**Step 4: Implement word-list CRUD endpoints**
- List, detail, add item, remove item, delete list with ownership checks.

**Step 5: Run focused backend API/task tests**
- Run: `docker compose -f docker-compose.test.yml run --rm --build test pytest backend/tests/test_word_lists_api.py backend/tests/test_import_jobs_api.py backend/tests/test_epub_processing.py backend/tests/test_imports_api.py -q`

---

### Task 4: Frontend Imports Wiring Tests (RED) + Implementation (GREEN)

**Files:**
- Create: `frontend/src/lib/imports-client.ts`
- Create: `frontend/src/app/imports/page.tsx`
- Create: `frontend/src/lib/__tests__/imports-client.test.ts`
- Create: `frontend/src/app/imports/__tests__/page.test.tsx`
- Modify: `frontend/src/lib/api-client.ts`
- Modify: `frontend/src/lib/auth-nav.tsx`
- Modify: `frontend/src/lib/auth-route-guard.ts`
- Modify: `frontend/src/middleware.ts`
- Modify: `frontend/src/app/__tests__/layout-auth-nav.test.tsx`
- Modify: `frontend/src/app/__tests__/page.test.tsx`

**Step 1: Add failing frontend tests**
- Multipart upload behavior (`FormData`) and status-aware response handling.
- Imports page upload/list/progress render behavior.
- Guard/nav coverage for `/imports`.

**Step 2: Implement minimal frontend wiring**
- Add import API client and `/imports` page with polling progress.
- Add nav link and protected-route coverage.

**Step 3: Run frontend verification**
- Run: `npm --prefix frontend run lint`
- Run: `npm --prefix frontend test -- --runInBand`

---

### Task 5: E2E/CI Coverage + Full Verification

**Files:**
- Modify: `e2e/tests/smoke/auth-guard.smoke.spec.ts`
- Create: `e2e/tests/smoke/import-domain.smoke.spec.ts`
- Optional Create: `e2e/tests/full/import-progress.spec.ts` (if deterministic seeding is implemented)

**Step 1: Add failing smoke coverage for new path**
- `/imports` protected-route checks.
- New import-domain smoke contract against `/api/word-lists/import` and `/api/import-jobs/{id}`.

**Step 2: Run smoke/full suites**
- Run: `npm --prefix e2e run test:smoke`
- Run: `npm --prefix e2e run test:full`

**Step 3: Full stack verification evidence**
- Run: `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"`
- Run: `npm --prefix frontend run lint`
- Run: `npm --prefix frontend test -- --runInBand`
- Run: `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /e2e && npm run test:smoke:ci"`
- Run: `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /e2e && npm run test:full"`

---

### Task 6: Status Board Update

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update workstream matrix row**
- Move “Word list + ePub import” from partial to reflect implemented domain/API/progress path and frontend wiring.

**Step 2: Update top-gap ordering**
- Promote next unresolved highest-priority gap.

**Step 3: Append evidence log entry**
- Add timestamped status-change row with command evidence.

---

## Execution Notes

1. Keep legacy `/api/imports` behavior stable unless tests prove a safe migration path.
2. Prefer deterministic tests that avoid timing assumptions about worker completion.
3. Do not claim completion without fresh verification output from all required commands.

---

## Completion Note (2026-03-06)

- Implemented full import-domain schema/model slice: `books`, `word_lists`, `word_list_items`, `import_jobs` plus migration `005`.
- Added backend API surface for import workflow and progress path:
  - `POST /api/word-lists/import`
  - `GET /api/import-jobs/{job_id}`
  - `GET /api/import-jobs/{job_id}/events` (SSE)
  - word-list CRUD endpoints under `/api/word-lists/*`
- Added new worker task `process_word_list_import` to persist books/lists/items and update import-job counters.
- Added frontend `/imports` page wiring (upload, import-job display, progress polling), plus multipart-safe API client behavior and protected-route/nav integration.
- Added E2E smoke coverage for the new import-domain contract and extended auth-guard smoke for `/imports`.

Verification evidence (fresh runs):
- `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` -> `127 passed`
- `npm --prefix frontend run lint` -> pass
- `npm --prefix frontend test -- --runInBand` -> `9 suites / 35 tests passed`
- `docker compose -f docker-compose.yml --profile tests exec -T backend alembic upgrade head` -> migrations `001..005` applied
- `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:smoke:ci"` -> `7 passed`
- `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:full"` -> `8 passed`
