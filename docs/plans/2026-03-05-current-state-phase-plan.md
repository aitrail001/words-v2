# Current-State Phase Plan (Evidence-Based)

**Status:** IN_PROGRESS  
**Date:** 2026-03-05  
**Scope:** Derived from current commits plus code/test files in `backend/` and `frontend/` (not from roadmap intent alone).

---

## Progress Update (2026-03-05)

- Import API reliability improvements are implemented (status-aware dedupe returns, enqueue-failure handling, and cleanup path hardening).
- Worker runtime now exists in `docker-compose.yml` (`worker` service) and was runtime-validated.
- `backend/tests/test_epub_processing.py` placeholder tests were replaced with real stop-word and lemmatization coverage.
- Learning queue models/migration, queue review APIs, and queue-based frontend review flow are implemented.
- Frontend auth token persistence now survives reload/navigation (`localStorage`-backed API client token storage).
- Playwright E2E project is implemented under `e2e/` with smoke and full scenarios.
- CI now includes required `e2e-smoke` on PR and `e2e-full` on push/workflow dispatch using Docker Compose stack + seeded fixtures.
- Backend and frontend test suites are green.

---

## Phase 0 Reality: Foundation Is In Place

**What is implemented now**
- Containerized local stack with Postgres, Redis, backend, frontend and CI pipelines.
- FastAPI app wiring includes lifecycle setup, Redis init/close, CORS, and rate limiting.
- Health endpoint checks both DB and Redis.

**Evidence**
- Infra/CI: `docker-compose.yml`, `.github/workflows/ci.yml`
- App foundation: `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/core/database.py`, `backend/app/core/redis.py`, `backend/app/core/logging.py`
- Health API + tests: `backend/app/api/health.py`, `backend/tests/test_health.py`

---

## Phase 1 Reality: Auth + Core Vocabulary (Mostly Implemented)

**What is implemented now**
- Core models + migration exist for users/words/meanings/translations.
- Auth endpoints implemented: register, login, me.
- Word endpoints implemented: search, detail, lookup (local DB only).
- Frontend has login/register pages and search UI.

**Evidence**
- Migration + models: `backend/alembic/versions/001_add_core_models.py`, `backend/app/models/user.py`, `backend/app/models/word.py`, `backend/app/models/meaning.py`, `backend/app/models/translation.py`
- API routers: `backend/app/api/auth.py`, `backend/app/api/words.py`
- Backend tests: `backend/tests/test_auth.py`, `backend/tests/test_words.py`, `backend/tests/test_models.py`, `backend/tests/test_security.py`
- Frontend pages/tests: `frontend/src/app/login/page.tsx`, `frontend/src/app/register/page.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/login/__tests__/page.test.tsx`, `frontend/src/app/register/__tests__/page.test.tsx`, `frontend/src/app/__tests__/page.test.tsx`

**Current gaps vs roadmap**
- No refresh/logout endpoints yet.
- `POST /api/words/lookup` explicitly returns 404 for misses (Dictionary API integration not implemented yet).
- No protected-route enforcement yet (token persistence exists, but route guards/session lifecycle are still basic).

---

## Phase 2 Reality: Review/SM-2 Slice Implemented (But Narrow)

**What is implemented now**
- Review persistence exists (`review_sessions`, `review_cards`) with migration.
- SM-2 algorithm integration is active in service layer.
- Review API supports session create, due cards read, card submit, session complete.
- Frontend review page exists with rating flow.

**Evidence**
- Migration + models: `backend/alembic/versions/002_add_review_models.py`, `backend/app/models/review.py`
- Algorithm + service: `backend/app/spaced_repetition.py`, `backend/app/services/review.py`
- API router: `backend/app/api/reviews.py`
- Backend tests: `backend/tests/test_review_models.py`, `backend/tests/test_review_service.py`, `backend/tests/test_review_api.py`
- Frontend page/tests: `frontend/src/app/review/page.tsx`, `frontend/src/app/review/__tests__/page.test.tsx`

**Current gaps vs roadmap**
- No explicit learning-queue model/endpoints (`user_meanings`, `review_history`) yet.
- No stats/history endpoints.
- No API path to add meanings into review pipeline from vocabulary flow.
- `cards_reviewed` is present on `ReviewSession` but not incremented in service logic.

---

## Phase 3 Reality: ePub Import Skeleton Exists (Early/Incomplete)

**What is implemented now**
- `epub_imports` model + migration exists.
- Import API supports upload, list, and detail status.
- Celery task parses ePub, runs spaCy, and creates top words.
- Content hash dedupe path exists for already-completed same-user imports.
- Import API reliability improvements are in place for dedupe, enqueue failures, and cleanup.
- Docker Compose includes a runnable `worker` service for Celery processing.

**Evidence**
- Migration + model: `backend/alembic/versions/003_add_epub_import.py`, `backend/app/models/epub_import.py`
- API + task wiring: `backend/app/api/imports.py`, `backend/app/tasks/epub_processing.py`, `backend/app/celery_app.py`, `backend/app/main.py`
- Tests: `backend/tests/test_epub_import_models.py`, `backend/tests/test_imports_api.py`, `backend/tests/test_epub_processing.py`
- Runtime worker: `docker-compose.yml`
- Commits introducing this slice: `b912e4e`, `ad415bf`, `7aae76b`

**Current gaps vs roadmap**
- No word-list domain yet (`books`, `word_lists`, `word_list_items`, import jobs, etc.).
- No SSE/WebSocket progress channel.

---

## Cross-Phase Gaps and Risks

- Phase ordering drift from the roadmap: review functionality landed before full word-list import workflow, creating integration mismatch.
- Working tree is currently dirty (tracked modifications and untracked files), so phase boundaries are not yet cleanly committed.
- Verification status improved: backend, frontend, Playwright smoke, and Playwright full suites are green in Docker-based verification (2026-03-05).
- ePub processing depends on `en_core_web_sm`; missing model will fail runtime imports.
- Frontend/backend version intent drift exists (`docs` mention Next.js 16, `frontend/package.json` is Next.js 15.1.0).

---

## Next 2 Implementation Slices

### Slice 1: Make ePub import runnable and test-complete (COMPLETED - 2026-03-05)

**Outcome**
- End-to-end import can be queued and processed reliably in local docker/dev.

**Evidence of completion**
- Import API now handles dedupe status-aware returns and enqueue-failure state handling/cleanup (`backend/app/api/imports.py`).
- Celery worker runtime is provisioned in Docker Compose and runtime-validated (`docker-compose.yml`).
- Placeholder ePub processing tests were replaced with real stop-word and lemmatization tests (`backend/tests/test_epub_processing.py`).
- Backend/frontend verification is green.

**Files touched**
- `docker-compose.yml`
- `backend/app/api/imports.py`
- `backend/app/tasks/epub_processing.py`
- `backend/tests/test_imports_api.py`
- `backend/tests/test_epub_processing.py`

### Slice 2: Bridge review to a real learning queue (COMPLETED - 2026-03-05)

**Outcome**
- Users can add meanings to a persistent queue, then review due items from that queue (not only pre-created raw cards).

**Evidence of completion**
- New persistence for queue membership + review history added via migration `004` (`backend/alembic/versions/004_add_learning_queue.py`).
- Queue APIs implemented in `backend/app/api/reviews.py`:
  - `POST /api/reviews/queue`
  - `GET /api/reviews/queue/due`
  - `POST /api/reviews/queue/{item_id}/submit`
  - `GET /api/reviews/queue/stats`
- Queue service logic implemented in `backend/app/services/review.py` with SM-2 submission handling and history writes.
- Frontend review flow now consumes queue due items and submits queue ratings (`frontend/src/app/review/page.tsx`).
- Backend and frontend tests are green after integration (`100 passed` backend, `5 suites / 16 tests passed` frontend).

**Files to touch**
- `backend/alembic/versions/004_add_learning_queue.py` (new)
- `backend/app/models/review.py` (or split new model files if preferred)
- `backend/app/services/review.py`
- `backend/app/api/reviews.py`
- `backend/tests/test_review_models.py`
- `backend/tests/test_review_service.py`
- `backend/tests/test_review_api.py`
- `frontend/src/app/review/page.tsx`
- `frontend/src/app/review/__tests__/page.test.tsx`

### Slice 3: Add required PR E2E smoke gate + full suite (COMPLETED - 2026-03-05)

**Outcome**
- Playwright E2E verification is now part of delivery gates: smoke on PR (required), full suite on main/workflow dispatch.

**Evidence of completion**
- New E2E project and tests:
  - `@smoke` register -> review empty-state flow
  - `@smoke` seeded due-item review submit flow
  - full dashboard seeded-word search flow
- Deterministic test data seeding SQL added for reproducible queue/search assertions.
- Docker Compose includes `playwright` test profile service.
- CI includes:
  - `e2e-smoke` (PR + push main, intended required check)
  - `e2e-full` (push main + workflow_dispatch)
  - artifacts upload + teardown on `always()`.
- Frontend got E2E-hardening updates:
  - token persistence in `api-client`
  - stable `data-testid` hooks and header navigation links.

**Files touched**
- `e2e/package.json`
- `e2e/package-lock.json`
- `e2e/playwright.config.ts`
- `e2e/tsconfig.json`
- `e2e/.gitignore`
- `e2e/scripts/seed.sql`
- `e2e/tests/helpers/auth.ts`
- `e2e/tests/helpers/review-seed.ts`
- `e2e/tests/smoke/register-review-empty.smoke.spec.ts`
- `e2e/tests/smoke/review-submit.smoke.spec.ts`
- `e2e/tests/full/dashboard-search.spec.ts`
- `.github/workflows/ci.yml`
- `docker-compose.yml`
- `frontend/src/lib/api-client.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/app/login/page.tsx`
- `frontend/src/app/register/page.tsx`
- `frontend/src/app/review/page.tsx`

---

## Verification Commands

```bash
# Backend setup + verification
cd backend
pip install -r requirements.txt -r requirements-test.txt
alembic upgrade head
pytest -q

# Frontend setup + verification
cd ../frontend
npm ci
npm run lint
npm test -- --runInBand --watch=false

# Optional smoke checks (app up)
cd ..
docker compose up -d postgres redis backend frontend
curl -s http://localhost:8000/api/health
```
