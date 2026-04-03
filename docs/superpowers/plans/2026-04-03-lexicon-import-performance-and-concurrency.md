# Lexicon Import Performance and Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make lexicon enrichment and voice imports scale to very large JSONL files with controlled DB load, single-active-job locking per `source_reference`, multi-job admin progress visibility, and phase timing metrics.

**Architecture:** Introduce a server-side source-reference lock for active import jobs, move enqueue/import paths to streaming summaries/processing, throttle worker progress commits, and surface timing-rich multi-job progress in admin pages. Preserve current import semantics while reducing memory pressure and write amplification.

**Tech Stack:** FastAPI, SQLAlchemy, Celery tasks, Python import tools, Next.js/React admin frontend, Jest/pytest.

---

### Task 1: Add source-reference lock and 409 API behavior

**Files:**
- Modify: `backend/app/api/lexicon_jobs.py`
- Modify: `backend/app/services/lexicon_jobs.py`
- Test: `backend/tests/test_lexicon_jobs_api.py`

- [ ] **Step 1: Write failing API tests for active same-source lock**

```python
# backend/tests/test_lexicon_jobs_api.py
# Add tests:
# - import_db returns 409 when active queued/running job exists for same source_reference
# - voice_import_db returns 409 when active queued/running job exists for same source_reference
# - same source_reference allowed after prior job completed
# - different source_reference allowed in parallel
```

- [ ] **Step 2: Run targeted test subset and verify RED**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q -k "source_reference or voice_import_db or import_db"`
Expected: FAIL for missing 409 lock behavior.

- [ ] **Step 3: Implement lock query + 409 response in API create endpoints**

```python
# backend/app/api/lexicon_jobs.py
# In create_import_db_job/create_voice_import_db_job:
# - normalize source_reference
# - call service helper: find_active_source_reference_job(...)
# - if found: raise HTTPException(status_code=409, detail=...)
```

- [ ] **Step 4: Implement service helper for active same-source lookup**

```python
# backend/app/services/lexicon_jobs.py
# Add helper that filters LexiconJob where:
# - job_type matches
# - status in ACTIVE_JOB_STATUSES
# - request_payload['source_reference'] == normalized value
# ordered newest first
```

- [ ] **Step 5: Run the same test subset and verify GREEN**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q -k "source_reference or voice_import_db or import_db"`
Expected: PASS.


### Task 2: Replace enqueue-time full-load summaries with streaming summaries

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/voice_import_db.py`
- Modify: `backend/app/api/lexicon_jobs.py`
- Test: `tools/lexicon/tests/test_import_db.py`
- Test: `tools/lexicon/tests/test_voice_import_db.py`

- [ ] **Step 1: Add failing tests for summary-from-path without full row list usage**

```python
# tools/lexicon/tests/test_import_db.py
# tools/lexicon/tests/test_voice_import_db.py
# Assert summary helpers count rows/types from file path directly.
```

- [ ] **Step 2: Run targeted tool tests and verify RED**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_import_db.py -q -k "summary"`
Expected: FAIL for missing path-based summary helpers.

- [ ] **Step 3: Implement streaming summary helpers**

```python
# tools/lexicon/import_db.py
# def summarize_compiled_rows_from_path(path: str | Path) -> dict[str, int]:
#   - iterate line-by-line via iter_compiled_rows
#   - count entry_type buckets

# tools/lexicon/voice_import_db.py
# def summarize_voice_manifest_rows_from_path(path: str | Path) -> dict[str, int]:
#   - iterate file line-by-line
#   - count generated/existing/failed + row_count
```

- [ ] **Step 4: Switch job-create endpoints to new summary helpers**

```python
# backend/app/api/lexicon_jobs.py
# remove load_*_rows() from enqueue path
# use summarize_*_from_path(...) directly
```

- [ ] **Step 5: Run same tests and verify GREEN**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_import_db.py -q -k "summary"`
Expected: PASS.


### Task 3: Throttle worker progress commits and add timing metrics

**Files:**
- Modify: `backend/app/tasks/lexicon_jobs.py`
- Modify: `backend/app/api/lexicon_jobs.py`
- Modify: `admin-frontend/src/lib/lexicon-jobs-client.ts`
- Test: `backend/tests/test_lexicon_worker_tasks.py`
- Test: `backend/tests/test_lexicon_jobs_api.py`

- [ ] **Step 1: Add failing worker tests for throttled commit behavior + timing fields**

```python
# backend/tests/test_lexicon_worker_tasks.py
# Add assertions:
# - commit count is bounded for many callbacks
# - request_payload.progress_timing contains elapsed/phase durations
```

- [ ] **Step 2: Run worker tests and verify RED**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_worker_tasks.py -q -k "progress or timing"`
Expected: FAIL for missing throttling/timing.

- [ ] **Step 3: Implement buffered progress flush helper in tasks**

```python
# backend/app/tasks/lexicon_jobs.py
# Add helper object/state for:
# - row-based flush interval (e.g. 100)
# - time-based flush interval (e.g. 1000ms)
# - force flush on phase transitions and terminal states
# Add progress_timing in request_payload:
# - queue_wait_ms
# - elapsed_ms
# - validation_elapsed_ms
# - import_elapsed_ms
```

- [ ] **Step 4: Expose timing fields through job response and TS types**

```python
# backend/app/api/lexicon_jobs.py
# Include progress_timing in response model and serializer.
```

```ts
// admin-frontend/src/lib/lexicon-jobs-client.ts
// Extend LexiconJob typing to include progress_timing.
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_worker_tasks.py backend/tests/test_lexicon_jobs_api.py -q -k "progress or timing"`
Expected: PASS.


### Task 4: Support multi-active job UX for import-db page and fix hydration mismatch

**Files:**
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Test: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

- [ ] **Step 1: Add failing frontend tests for multi-active jobs and hydration-safe context**

```tsx
// import-db page tests
// - renders multiple running/queued jobs in Import progress section
// - no render-time window.search dependent branch mismatch
// - keeps recent jobs panel intact
```

- [ ] **Step 2: Run import-db page tests and verify RED**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx`
Expected: FAIL for current single-job assumptions.

- [ ] **Step 3: Refactor page state model to activeJobs[] + tracked IDs**

```tsx
// import-db/page.tsx
// - replace single job with activeJobs array
// - localStorage key: lexicon-import-db-active-jobs (JSON array)
// - poll active ids and reconcile terminal jobs
// - move hasContext derivation to state set in useEffect only
```

- [ ] **Step 4: Add timing metric display in active/recent cards**

```tsx
// import-db/page.tsx
// show:
// - elapsed
// - validation elapsed
// - import elapsed
// - queue wait
```

- [ ] **Step 5: Run page tests and verify GREEN**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx`
Expected: PASS.


### Task 5: Support multi-active job UX for voice-import page + 409 lock messaging

**Files:**
- Modify: `admin-frontend/src/app/lexicon/voice-import/page.tsx`
- Test: `admin-frontend/src/app/lexicon/voice-import/__tests__/page.test.tsx`

- [ ] **Step 1: Add failing tests for multi-active voice jobs and lock conflict message**

```tsx
// voice-import page tests
// - renders multiple active jobs cards
// - shows 409 source-reference lock detail when create fails
// - keeps dry-run and recent jobs behavior
```

- [ ] **Step 2: Run voice page tests and verify RED**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/voice-import/__tests__/page.test.tsx`
Expected: FAIL for current single-active-job behavior.

- [ ] **Step 3: Implement activeJobs[] model + tracked IDs + lock banner**

```tsx
// voice-import/page.tsx
// - localStorage key: lexicon-voice-import-active-jobs (JSON array)
// - render active jobs list with progress/timing
// - handle 409 error from create API and show explicit source_reference lock message
```

- [ ] **Step 4: Run voice page tests and verify GREEN**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/voice-import/__tests__/page.test.tsx`
Expected: PASS.


### Task 6: Documentation/status updates for the new runtime contract

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `docs/plans/2026-03-30-voice-import-and-progress.md` (or add follow-up plan note)

- [ ] **Step 1: Add status entry for source-reference lock + throttled progress + multi-job UI + timing metrics**

```md
# docs/status/project-status.md
# Add dated row with verification commands and outcomes.
```

- [ ] **Step 2: Add/adjust plan notes for operator expectations**

```md
# docs/plans/...
# Document that same source_reference cannot run concurrently.
```

- [ ] **Step 3: Verify docs mention lock semantics and timing fields**

Run: `rg -n "source_reference|409|timing|elapsed|active jobs" docs/status/project-status.md docs/plans/2026-03-30-voice-import-and-progress.md`
Expected: matching lines present.


### Task 7: Final verification bundle

**Files:**
- Test only

- [ ] **Step 1: Backend focused verification**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: PASS.

- [ ] **Step 2: Lexicon tool verification**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_import_db.py -q`
Expected: PASS.

- [ ] **Step 3: Frontend verification**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/voice-import/__tests__/page.test.tsx`
Expected: PASS.

- [ ] **Step 4: Optional E2E smoke for import flows**

Run: `pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts --project=chromium`
Expected: PASS.
