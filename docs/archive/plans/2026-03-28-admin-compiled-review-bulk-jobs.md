# Admin Compiled Review Bulk Jobs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move compiled-review bulk approval/rejection/reopen actions to background lexicon jobs with progress UI, and convert the compiled-review item view to paginated server-side loading so large batches no longer return or hydrate whole-batch item payloads.

**Architecture:** Reuse the existing `lexicon_jobs` framework for queued bulk review work, refactor compiled-review decision logic into shared backend helpers, and change the admin frontend to operate on paginated item envelopes plus job polling. Keep export/materialize behavior intact while removing the synchronous full-batch bulk-update dependency from the UI.

**Tech Stack:** FastAPI, SQLAlchemy, Celery, PostgreSQL, React, Next.js, Jest, Pytest, Playwright.

---

### Task 1: Add failing backend tests for paginated compiled-review items and async bulk jobs

**Files:**
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Modify: `backend/tests/test_lexicon_jobs_api.py`
- Modify: `backend/tests/test_lexicon_worker_tasks.py`

**Step 1: Write the failing API tests for paginated item listing**

Add tests that expect:
- `GET /api/lexicon-compiled-reviews/batches/{batch_id}/items?limit=2&offset=0`
- a paginated envelope with `items`, `total`, `limit`, `offset`, `has_more`
- filtering by `status`
- searching by `search`

**Step 2: Run the focused compiled-review API tests to verify red**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py -q`
Expected: FAIL because the endpoint still returns a raw array.

**Step 3: Write the failing lexicon-job API test for compiled-review bulk jobs**

Add a test that expects:
- `POST /api/lexicon-jobs/compiled-review-bulk-update`
- `202 Accepted`
- `job_type == "compiled_review_bulk_update"`
- enqueue call to the new worker task

**Step 4: Run the focused lexicon-jobs API tests to verify red**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
Expected: FAIL because the route and enqueue path do not exist yet.

**Step 5: Write the failing worker-task test for compiled-review bulk processing**

Add a test that expects:
- the worker loads pending items
- updates progress
- changes review status in chunks
- writes summary counts into `result_payload`

**Step 6: Run the focused worker-task tests to verify red**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_worker_tasks.py -q`
Expected: FAIL because the worker task does not exist yet.

### Task 2: Implement backend pagination and shared compiled-review decision helpers

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Create: `backend/app/services/lexicon_compiled_review_decisions.py`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`

**Step 1: Extract shared item-decision logic into a service helper**

Move the single-item review-status mutation rules into a reusable service so the worker and API use one code path.

**Step 2: Add paginated response models and query handling to compiled-review items**

Implement:
- `status`
- `search`
- `limit`
- `offset`
- deterministic ordering
- envelope response fields

**Step 3: Keep single-item update behavior working against the shared helper**

Refactor the patch endpoint to call the shared decision helper and recalculate/update batch counters safely.

**Step 4: Run compiled-review API tests**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py -q`
Expected: PASS for the new pagination tests and no regression in existing item-update behavior.

### Task 3: Implement compiled-review bulk jobs in backend API and Celery worker

**Files:**
- Modify: `backend/app/api/lexicon_jobs.py`
- Modify: `backend/app/tasks/lexicon_jobs.py`
- Modify: `backend/app/services/lexicon_jobs.py`
- Modify: `backend/app/models/lexicon_job.py` only if job typing hints need widening
- Modify: `backend/tests/test_lexicon_jobs_api.py`
- Modify: `backend/tests/test_lexicon_worker_tasks.py`

**Step 1: Add request model and route for compiled-review bulk jobs**

Implement `POST /api/lexicon-jobs/compiled-review-bulk-update` with:
- `batch_id`
- `review_status`
- `decision_reason`
- `scope`

**Step 2: Add worker task `run_lexicon_compiled_review_bulk_update`**

Use chunked processing and `apply_lexicon_job_progress()` after each chunk.

**Step 3: Reuse the shared compiled-review decision helper in the worker**

Avoid duplicate mutation logic between the patch endpoint and the worker.

**Step 4: Complete jobs with compact summary payloads**

Populate:
- `processed_count`
- `approved_count`
- `rejected_count`
- `pending_count`
- `failed_count`
- `review_status`
- `batch_id`

**Step 5: Run focused lexicon-jobs API and worker tests**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: PASS.

### Task 4: Add failing frontend tests for paginated compiled-review items and async bulk progress UX

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/__tests__/lexicon-compiled-reviews-client.test.ts`
- Modify: `admin-frontend/src/lib/__tests__/lexicon-jobs-client.test.ts` if present, else create it

**Step 1: Add failing client test for paginated item listing contract**

Expect the client to call the items endpoint with query params and consume an envelope, not a raw array.

**Step 2: Add failing client test for compiled-review bulk job creation**

Expect `createCompiledReviewBulkUpdateLexiconJob()` to hit `/lexicon-jobs/compiled-review-bulk-update`.

**Step 3: Add failing page test for bulk approve progress flow**

Expect:
- user clicks `Approve All`
- job is created
- page polls `getLexiconJob()`
- progress text appears
- on completion, current page and batch summary reload

**Step 4: Run the focused admin frontend tests to verify red**

Run: `cd admin-frontend && npm test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/lib/__tests__/lexicon-compiled-reviews-client.test.ts`
Expected: FAIL because the client/page still assume synchronous bulk update and raw item arrays.

### Task 5: Implement frontend paginated compiled-review loading and async bulk-job UX

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-compiled-reviews-client.ts`
- Modify: `admin-frontend/src/lib/lexicon-jobs-client.ts`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/__tests__/lexicon-compiled-reviews-client.test.ts`
- Modify: `admin-frontend/src/lib/__tests__/lexicon-jobs-client.test.ts` if used

**Step 1: Update the compiled-review client to use paginated list envelopes**

Add typed request params for:
- `limit`
- `offset`
- `status`
- `search`

**Step 2: Add a client helper for compiled-review bulk job creation**

Implement a typed function wrapping `/lexicon-jobs/compiled-review-bulk-update`.

**Step 3: Refactor the page state to page-local item storage**

Replace the whole-batch array model with:
- current page items
- total count
- page offset
- page size
- active job state

**Step 4: Replace synchronous bulk-update flow with job creation and polling**

On confirmation:
- create job
- close modal
- show progress
- on completion, refresh batch summary and current page only

**Step 5: Keep single-item review and materialize flows working**

Do not regress:
- per-item approve/reject/reopen
- reviewed-output materialize job polling
- export buttons

**Step 6: Run focused frontend tests**

Run: `cd admin-frontend && npm test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/lib/__tests__/lexicon-compiled-reviews-client.test.ts`
Expected: PASS.

### Task 6: Add E2E coverage for compiled-review bulk progress and keep admin flow green

**Files:**
- Create or Modify: `e2e/tests/smoke/admin-compiled-review-bulk-job.smoke.spec.ts`
- Modify only if needed: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`

**Step 1: Write the E2E flow**

Cover:
- open compiled-review admin tool
- trigger `Approve All`
- observe async progress UI
- wait for completion
- verify refreshed counts

**Step 2: Run the new E2E test to verify red if needed, then green after implementation**

Run: `docker compose -f docker-compose.yml exec -T admin-frontend sh -lc 'cd /app && npm run test -- --runInBand'` only if unit fixtures need syncing, then run Playwright from the standard test path used in this repo.

**Step 3: Run the targeted smoke in Docker**

Run: `docker compose -f docker-compose.yml exec -T admin-frontend sh -lc 'cd /app && true'` if needed to confirm app availability, then run the Playwright smoke command already used in this repo for admin flows.
Expected: PASS.

### Task 7: Run verification, update status, and prepare the branch for review

**Files:**
- Modify: `docs/status/project-status.md`
- Modify if needed: `docs/plans/2026-03-28-admin-compiled-review-bulk-jobs-design.md`

**Step 1: Run backend verification**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: PASS.

**Step 2: Run admin frontend verification**

Run: `cd admin-frontend && npm run lint && npm test -- --runInBand`
Expected: PASS.

**Step 3: Run targeted E2E verification**

Run the compiled-review/admin smoke path in the same Docker-backed pattern used by this repo.
Expected: PASS.

**Step 4: Update live project status with fresh evidence**

Record:
- new async bulk-review job support
- paginated compiled-review admin loading
- exact test/E2E evidence

**Step 5: Commit**

```bash
git add backend/app/api/lexicon_compiled_reviews.py backend/app/api/lexicon_jobs.py backend/app/tasks/lexicon_jobs.py backend/app/services/lexicon_compiled_review_decisions.py backend/app/services/lexicon_jobs.py backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py admin-frontend/src/lib/lexicon-compiled-reviews-client.ts admin-frontend/src/lib/lexicon-jobs-client.ts admin-frontend/src/app/lexicon/compiled-review/page.tsx admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx admin-frontend/src/lib/__tests__/lexicon-compiled-reviews-client.test.ts e2e/tests/smoke/admin-compiled-review-bulk-job.smoke.spec.ts docs/plans/2026-03-28-admin-compiled-review-bulk-jobs-design.md docs/plans/2026-03-28-admin-compiled-review-bulk-jobs.md docs/status/project-status.md
git commit -m "feat: async compiled review bulk jobs"
```
