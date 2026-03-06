# Import Completion Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** COMPLETED  
**Date:** 2026-03-06  
**Goal:** Ensure EPUB imports complete successfully even when `en_core_web_sm` is unavailable, and add E2E coverage that verifies terminal import completion with a valid EPUB.

**Architecture:** Keep existing import-job state machine and API contracts. Refactor worker NLP extraction into a shared helper that prefers `en_core_web_sm`, falls back to `spacy.blank("en")` when the model is missing, and only fails on true parsing/runtime errors. Add regression tests in backend worker tests and add full E2E polling against `/api/import-jobs/{id}` using a real EPUB fixture.

**Tech Stack:** FastAPI, SQLAlchemy, Celery, spaCy, pytest, Next.js/Playwright E2E, Docker Compose.

---

## Design Alignment (Brief)

1. Problem statement:
- Current worker behavior raises on missing `en_core_web_sm`, producing terminal `failed` imports in real runtime.
- Existing smoke tests only validate enqueue/snapshot and miss asynchronous terminal failure.

2. Approaches considered:
- A) Install `en_core_web_sm` in container image only. Fast but brittle for CI/runtime drift and heavier image pulls.
- B) Worker fallback path (`spacy.blank("en")` and safe token handling) plus regression tests. More robust and keeps behavior stable under model-missing conditions.
- C) Fail closed and document model requirement. Not acceptable for product reliability.

3. Chosen approach:
- Use B. Keep imports functional under degraded NLP and verify terminal completion with backend + full E2E tests.

---

### Task 1: Backend Regression Tests First (RED)

**Files:**
- Modify: `backend/tests/test_epub_processing.py`

**Steps:**
1. Add failing test for `extract_epub_vocabulary` when `spacy.load` raises `OSError`, asserting completion via fallback.
2. Add failing test for `process_word_list_import` with the same missing-model scenario, asserting terminal `completed` and non-error counters.
3. Run targeted pytest command and confirm failures are due to current hard-fail behavior.

---

### Task 2: Worker Fallback Implementation (GREEN)

**Files:**
- Modify: `backend/app/tasks/epub_processing.py`

**Steps:**
1. Add a shared helper to build word frequencies with preferred model load + fallback mode.
2. Reuse helper in both import workers (`extract_epub_vocabulary` and `process_word_list_import`).
3. Keep failure path only for true parse/runtime errors; do not fail solely on missing model.
4. Re-run targeted backend tests and confirm GREEN.

---

### Task 3: Full E2E Terminal Completion Coverage (RED -> GREEN)

**Files:**
- Create: `e2e/tests/fixtures/epub/valid-minimal.epub`
- Create: `e2e/tests/helpers/import-jobs.ts`
- Create: `e2e/tests/full/import-terminal.full.spec.ts`

**Steps:**
1. Add failing full E2E test that uploads a valid EPUB and polls `/api/import-jobs/{id}` to terminal state.
2. Assert terminal status is `completed`, with non-empty counters and linked `book_id`/`word_list_id`.
3. Implement helper/fixture wiring needed to make the test deterministic.
4. Run target full test to confirm GREEN.

---

### Task 4: Verification + Documentation Evidence

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `docs/plans/2026-03-06-import-completion-hardening.md`

**Steps:**
1. Run full scoped verification: backend tests, frontend lint/tests, smoke E2E, full E2E.
2. Update project status board with changed reality/evidence and next priorities.
3. Mark this plan `COMPLETED` with exact command evidence.

---

## Verification Commands

```bash
# Targeted backend regression tests
pytest backend/tests/test_epub_processing.py -q

# Full backend suite
docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"

# Frontend quality gates
npm --prefix frontend run lint
npm --prefix frontend test -- --runInBand

# E2E smoke + full
npm --prefix e2e run test:smoke:ci
npm --prefix e2e run test:full
```

---

## Completion Note (2026-03-06)

- Added backend regression tests for missing spaCy model in both import workers:
  - `extract_epub_vocabulary` fallback completion
  - `process_word_list_import` fallback completion
- Implemented resilient NLP extraction helper in worker tasks:
  - prefer `en_core_web_sm`
  - fallback to `spacy.blank("en")`
  - defensive regex fallback if spaCy pipeline initialization fails
- Added full E2E terminal import coverage with a valid EPUB fixture and polling helper.
- During E2E RED run, identified and fixed a second root cause:
  - backend persisted uploads to `/tmp/words_uploads` (container-local), while worker consumed task path in a different container
  - introduced shared upload-dir resolver (`/app/uploads` with fallback) and updated both import APIs.

Verification evidence (fresh runs):
- `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest tests/test_epub_processing.py -q"` -> `6 passed`
- `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest tests/test_epub_processing.py tests/test_word_lists_api.py tests/test_imports_api.py -q"` -> `17 passed`
- `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` -> `129 passed`
- `npm --prefix frontend run lint` -> pass
- `npm --prefix frontend test -- --runInBand` -> `9 suites / 35 tests passed`
- `docker compose -f docker-compose.yml --profile tests exec -T backend alembic upgrade head` -> migrations `001..005` applied
- `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:smoke:ci"` -> `7 passed`
- `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:full"` -> `9 passed`
