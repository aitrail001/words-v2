# Lexicon Worker Jobs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move lexicon `import-db`, JSONL Review `materialize`, and Compiled Review `materialize` onto the existing Celery worker stack with a dedicated lexicon job model and polling status API.

**Architecture:** Add a lexicon-specific DB-backed job model instead of overloading the EPUB-oriented `ImportJob` table. The backend remains the control plane for validation, job creation, dedupe, and status reads, while Celery tasks in the worker execute the heavy file/DB operations and update durable progress state.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, Redis, Next.js admin frontend, Jest, Playwright, pytest.

---

### Task 1: Add Lexicon Job Model And Migration

**Files:**
- Create: `backend/app/models/lexicon_job.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<new_revision>_add_lexicon_jobs.py`
- Test: `backend/tests/test_models.py`

**Step 1: Write the failing test**

Add a model test that constructs a lexicon job and asserts default status/progress values plus `job_type` and `target_key` persistence.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py -q
```

Expected: FAIL because `LexiconJob` does not exist yet.

**Step 3: Write minimal implementation**

- add `LexiconJob` SQLAlchemy model
- register it in model exports
- add Alembic migration creating the table with:
  - ids / timestamps
  - created_by FK
  - job_type
  - status
  - target_key
  - request/result JSON payloads
  - progress fields
  - error message

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/models/lexicon_job.py backend/app/models/__init__.py backend/alembic/versions backend/tests/test_models.py
git commit -m "feat: add lexicon job model"
```

### Task 2: Add Lexicon Job Service Helpers

**Files:**
- Create: `backend/app/services/lexicon_jobs.py`
- Test: `backend/tests/test_lexicon_jobs_service.py`

**Step 1: Write the failing test**

Add service tests covering:
- create job
- reuse active job by `target_key`
- progress update
- success/failure finalization

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_service.py -q
```

Expected: FAIL because service helpers do not exist.

**Step 3: Write minimal implementation**

Implement helpers for:
- `create_or_reuse_lexicon_job(...)`
- `get_lexicon_job(...)`
- `mark_lexicon_job_started(...)`
- `update_lexicon_job_progress(...)`
- `complete_lexicon_job(...)`
- `fail_lexicon_job(...)`

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_service.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/lexicon_jobs.py backend/tests/test_lexicon_jobs_service.py
git commit -m "feat: add lexicon job service helpers"
```

### Task 3: Add Celery Lexicon Tasks

**Files:**
- Create: `backend/app/tasks/lexicon_jobs.py`
- Modify: `backend/app/celery_app.py`
- Test: `backend/tests/test_lexicon_worker_tasks.py`

**Step 1: Write the failing test**

Add task tests for:
- import-db task updates progress and completes
- JSONL materialize task completes with output paths
- Compiled materialize task completes with output paths
- failure path stores error message

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_worker_tasks.py -q
```

Expected: FAIL because lexicon worker tasks are missing.

**Step 3: Write minimal implementation**

- add Celery tasks for:
  - `run_lexicon_import_db`
  - `run_lexicon_jsonl_materialize`
  - `run_lexicon_compiled_materialize`
- include new task module in Celery app
- tasks call service helpers for lifecycle updates
- tasks reuse existing lexicon import/materialize logic rather than reimplementing it

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_worker_tasks.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/tasks/lexicon_jobs.py backend/app/celery_app.py backend/tests/test_lexicon_worker_tasks.py
git commit -m "feat: add lexicon celery tasks"
```

### Task 4: Add Lexicon Job API

**Files:**
- Create: `backend/app/api/lexicon_jobs.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_lexicon_jobs_api.py`

**Step 1: Write the failing test**

Add API tests covering:
- create import-db job
- create JSONL materialize job
- create compiled materialize job
- get job status
- reuse active job for same target
- return `503` if queue enqueue fails

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q
```

Expected: FAIL because API endpoints do not exist.

**Step 3: Write minimal implementation**

Add:
- `POST /api/lexicon-jobs/import-db`
- `POST /api/lexicon-jobs/jsonl-materialize`
- `POST /api/lexicon-jobs/compiled-materialize`
- `GET /api/lexicon-jobs/{job_id}`

The API should:
- validate and resolve paths/batches
- compute `target_key`
- create/reuse a lexicon job
- enqueue the correct Celery task
- return job status payloads

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/lexicon_jobs.py backend/app/main.py backend/tests/test_lexicon_jobs_api.py
git commit -m "feat: add lexicon jobs api"
```

### Task 5: Migrate Import DB Frontend To Lexicon Jobs

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-imports-client.ts`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Test: `admin-frontend/src/lib/__tests__/...` if needed

**Step 1: Write the failing test**

Update page tests so `Import DB`:
- starts via the new lexicon job API
- polls status
- reconnects to active job
- renders terminal result

**Step 2: Run test to verify it fails**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: FAIL because client/page still use old endpoint shapes.

**Step 3: Write minimal implementation**

- switch client to new lexicon job endpoints
- poll `GET /api/lexicon-jobs/{job_id}`
- preserve reconnect semantics from current page
- remove the temporary in-process-only assumptions

**Step 4: Run test to verify it passes**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: PASS.

**Step 5: Commit**

```bash
git add admin-frontend/src/lib/lexicon-imports-client.ts admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx
git commit -m "feat: move lexicon import db to worker jobs"
```

### Task 6: Migrate JSONL Review Materialize To Lexicon Jobs

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py` if old direct materialize path is retired or wrapped

**Step 1: Write the failing test**

Update page/API tests to expect job-based materialize creation and polling instead of inline materialization.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jsonl_reviews_api.py -q
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx
```

Expected: FAIL for the old direct materialize behavior.

**Step 3: Write minimal implementation**

- switch JSONL materialize action to the lexicon job API
- keep the existing reviewed-output UI, but populate it from terminal `result_payload`

**Step 4: Run test to verify it passes**

Run the same commands again and confirm PASS.

**Step 5: Commit**

```bash
git add admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts admin-frontend/src/app/lexicon/jsonl-review/page.tsx admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx backend/tests/test_lexicon_jsonl_reviews_api.py
git commit -m "feat: move jsonl materialize to worker jobs"
```

### Task 7: Migrate Compiled Review Materialize To Lexicon Jobs

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-compiled-reviews-client.ts`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`

**Step 1: Write the failing test**

Update compiled review tests to expect job-based materialization and polling.

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py -q
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx
```

Expected: FAIL for old direct materialize behavior.

**Step 3: Write minimal implementation**

- switch compiled review materialize to lexicon job creation/status
- preserve current reviewed-output presentation using job result payload

**Step 4: Run test to verify it passes**

Run the same commands again and confirm PASS.

**Step 5: Commit**

```bash
git add admin-frontend/src/lib/lexicon-compiled-reviews-client.ts admin-frontend/src/app/lexicon/compiled-review/page.tsx admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx backend/tests/test_lexicon_compiled_reviews_api.py
git commit -m "feat: move compiled materialize to worker jobs"
```

### Task 8: Make Worker Data Mounts Correct For Lexicon Writes

**Files:**
- Modify: `docker-compose.yml`
- Test: Playwright smoke + any dockerized verification path

**Step 1: Write the failing test**

Use the existing smoke path expectations around lexicon materialize/import worker execution. The test should fail if the worker cannot write under `/app/data`.

**Step 2: Run test to verify it fails**

Run the relevant smoke test after switching execution to worker if mounts are still read-only.

**Step 3: Write minimal implementation**

- ensure worker has writable `./data:/app/data` where lexicon reviewed outputs/import writes are expected
- keep backend mount choice consistent with control-plane needs

**Step 4: Run test to verify it passes**

Re-run the same smoke test and confirm PASS.

**Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: allow worker lexicon data writes"
```

### Task 9: Add Or Update Playwright Smoke Coverage

**Files:**
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`
- Modify: `e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts`
- Modify: `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`

**Step 1: Write the failing test**

Ensure smoke coverage explicitly verifies:
- Import DB reconnect still works through the worker-backed path
- JSONL materialize reaches terminal result through worker-backed path
- Compiled materialize reaches terminal result through worker-backed path

**Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose.yml exec -T playwright sh -lc "cd /workspace/e2e && E2E_BASE_URL=http://frontend:3000 E2E_API_URL=http://backend:8000/api E2E_ADMIN_URL=http://admin-frontend:3001 npx playwright test tests/smoke/admin-compiled-review-flow.smoke.spec.ts tests/smoke/admin-jsonl-review-flow.smoke.spec.ts tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts --project=chromium"
```

Expected: FAIL until assertions match the new worker-backed terminal flow.

**Step 3: Write minimal implementation**

Adjust smoke assertions to observe durable worker-backed job completion rather than old inline request completion assumptions.

**Step 4: Run test to verify it passes**

Run the same command again and confirm PASS.

**Step 5: Commit**

```bash
git add e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts
git commit -m "test: cover worker-backed lexicon jobs"
```

### Task 10: Final Verification And Documentation

**Files:**
- Modify: `docs/status/project-status.md`
- Optionally modify: `docs/decisions/` if a durable ADR is warranted

**Step 1: Run backend verification**

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_lexicon_jobs_service.py backend/tests/test_lexicon_worker_tasks.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jsonl_reviews_api.py backend/tests/test_lexicon_compiled_reviews_api.py -q
```

Expected: PASS.

**Step 2: Run frontend verification**

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend run lint
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend run build
```

Expected: PASS.

**Step 3: Run Playwright smoke**

```bash
docker compose -f /Users/johnson/AI/src/words-v2/docker-compose.yml exec -T playwright sh -lc "cd /workspace/e2e && E2E_BASE_URL=http://frontend:3000 E2E_API_URL=http://backend:8000/api E2E_ADMIN_URL=http://admin-frontend:3001 npx playwright test tests/smoke/admin-compiled-review-flow.smoke.spec.ts tests/smoke/admin-jsonl-review-flow.smoke.spec.ts tests/smoke/admin-db-inspector-flow.smoke.spec.ts tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts --project=chromium"
```

Expected: PASS.

**Step 4: Update status**

Record the worker migration and exact verification evidence in `docs/status/project-status.md`.

**Step 5: Commit**

```bash
git add docs/status/project-status.md
git commit -m "docs: record lexicon worker job migration"
```
