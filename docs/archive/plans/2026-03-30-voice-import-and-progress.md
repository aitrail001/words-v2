# Voice Import and Progress Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make import progress phase-aware, add admin voice import with progress/history, simplify voice policy editing, and expose explicit voice path information in DB Inspector.

**Architecture:** Keep DB import and voice import as separate backend engines, but align them around the same admin operator model. Additive job/result fields drive the UI; existing endpoints remain compatible where possible. Voice import reuses the lexicon jobs system rather than inventing a separate async framework.

**Tech Stack:** FastAPI, SQLAlchemy, Celery worker tasks, Python CLI tools, Next.js admin frontend, Playwright, pytest.

---

### Task 1: Add failing tests for import-db phase-aware progress counters

**Files:**
- Modify: `backend/tests/test_lexicon_jobs_api.py`
- Modify: `backend/tests/test_lexicon_worker_tasks.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing tests**
- Add tests asserting import preflight/import progress produce additive counters for validation/import/skipped/failed.
- Add a test asserting skip-existing progress updates current label and counters.

**Step 2: Run tests to verify they fail**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: failing assertions for missing counter fields/behavior.

**Step 3: Write minimal implementation**
- Extend import-db progress/result payload handling in tool/worker layers.
- Preserve backward-compatible job response shape.

**Step 4: Run tests to verify they pass**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py tools/lexicon/tests/test_import_db.py tools/lexicon/import_db.py backend/app/tasks/lexicon_jobs.py backend/app/api/lexicon_jobs.py
git commit -m "feat(lexicon): add phase-aware import progress"
```

### Task 2: Add failing tests for Lexicon Voice loading visibility and policy editor behavior

**Files:**
- Modify: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice/voice-storage-panel.tsx`

**Step 1: Write the failing tests**
- Add tests asserting visible loading state while runs/policies/detail are loading.
- Add tests asserting the policy editor is hidden until `Edit policy` is clicked.
- Add test asserting no radio select UI remains.
- Add test asserting apply path is callable even with unchanged displayed values.

**Step 2: Run tests to verify they fail**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice`
Expected: FAIL.

**Step 3: Write minimal implementation**
- Add loading UI.
- Remove redundant policy selection UI.
- Gate editor rendering behind explicit edit action.
- Ensure apply is not blocked by dirty-check assumptions.

**Step 4: Run tests to verify they pass**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice`
Expected: PASS.

**Step 5: Commit**
```bash
git add admin-frontend/src/app/lexicon/voice/page.tsx admin-frontend/src/app/lexicon/voice/voice-storage-panel.tsx admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx
git commit -m "feat(lexicon): clarify voice page loading and policy editing"
```

### Task 3: Add failing tests for DB Inspector explicit voice path display

**Files:**
- Modify: `backend/tests/test_lexicon_inspector_api.py`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`
- Modify: `backend/app/api/lexicon_inspector.py`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Modify: `admin-frontend/src/lib/lexicon-inspector-client.ts`

**Step 1: Write the failing tests**
- Add backend tests asserting per-scope voice path/resolution fields are returned.
- Add frontend tests asserting word/definition/example voice paths render explicitly.

**Step 2: Run tests to verify they fail**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py -q && pnpm --dir admin-frontend test -- --runInBand db-inspector`
Expected: FAIL.

**Step 3: Write minimal implementation**
- Extend inspector API shape additively.
- Render explicit scope sections/rows in the page.

**Step 4: Run tests to verify they pass**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py -q && pnpm --dir admin-frontend test -- --runInBand db-inspector`
Expected: PASS.

**Step 5: Commit**
```bash
git add backend/tests/test_lexicon_inspector_api.py backend/app/api/lexicon_inspector.py admin-frontend/src/app/lexicon/db-inspector/page.tsx admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx admin-frontend/src/lib/lexicon-inspector-client.ts
git commit -m "feat(lexicon): expose voice paths in db inspector"
```

### Task 4: Add failing tests for voice import CLI/backend behavior

**Files:**
- Modify: `tools/lexicon/tests/test_voice_import_db.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `backend/tests/test_lexicon_imports_api.py`
- Modify: `backend/tests/test_lexicon_jobs_api.py`
- Modify: `backend/tests/test_lexicon_worker_tasks.py`

**Step 1: Write the failing tests**
- Add tests for voice import dry run with `fail|skip|upsert` and `fail_fast|continue`.
- Add tests for progress callback labels/counters in `voice_import_db`.
- Add tests for async job creation/list/detail for `voice_import_db`.

**Step 2: Run tests to verify they fail**
Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_import_db.py tools/lexicon/tests/test_cli.py -q && PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: FAIL.

**Step 3: Write minimal implementation**
- Extend `voice_import_db.py` for preflight/progress/conflict+error modes.
- Add API endpoints and worker job type.
- Keep request/response patterns aligned with DB import.

**Step 4: Run tests to verify they pass**
Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_import_db.py tools/lexicon/tests/test_cli.py -q && PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py -q`
Expected: PASS.

**Step 5: Commit**
```bash
git add tools/lexicon/tests/test_voice_import_db.py tools/lexicon/tests/test_cli.py tools/lexicon/voice_import_db.py tools/lexicon/cli.py backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py backend/app/api/lexicon_imports.py backend/app/api/lexicon_jobs.py backend/app/tasks/lexicon_jobs.py
git commit -m "feat(lexicon): add voice import jobs and dry runs"
```

### Task 5: Add failing tests for admin voice import flow from recent voice runs

**Files:**
- Modify: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`
- Create: `admin-frontend/src/app/lexicon/voice-import/page.tsx`
- Create: `admin-frontend/src/app/lexicon/voice-import/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts`
- Modify: `admin-frontend/src/lib/lexicon-jobs-client.ts`
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`
- Create or modify: a voice import smoke spec under `e2e/tests/smoke/`

**Step 1: Write the failing tests**
- Add frontend tests asserting run cards expose `Import voice assets`.
- Add tests for voice import page mirroring DB import controls and recent job/history behavior.
- Add targeted Playwright assertion for launch from recent runs into voice import.

**Step 2: Run tests to verify they fail**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice lexicon/voice-import && pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts --project=chromium`
Expected: FAIL.

**Step 3: Write minimal implementation**
- Add voice import admin page.
- Add run action from voice page.
- Reuse current-progress/current-result/recent-jobs pattern.

**Step 4: Run tests to verify they pass**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice lexicon/voice-import && pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts --project=chromium`
Expected: PASS.

**Step 5: Commit**
```bash
git add admin-frontend/src/app/lexicon/voice/page.tsx admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx admin-frontend/src/app/lexicon/voice-import/page.tsx admin-frontend/src/app/lexicon/voice-import/__tests__/page.test.tsx admin-frontend/src/lib/lexicon-ops-client.ts admin-frontend/src/lib/lexicon-jobs-client.ts e2e/tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts
git commit -m "feat(lexicon): add admin voice import flow"
```

### Task 6: Update docs and status, then run final verification

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Update docs**
- Document phase-aware import progress.
- Document voice import CLI/admin workflow.
- Record verification evidence in project status.

**Step 2: Run focused verification**
Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_import_db.py tools/lexicon/tests/test_cli.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py backend/tests/test_lexicon_worker_tasks.py backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_inspector_api.py -q`
- `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db lexicon/voice lexicon/voice-import db-inspector`
- `pnpm --dir admin-frontend exec eslint src/app/lexicon/import-db/page.tsx src/app/lexicon/voice/page.tsx src/app/lexicon/voice/voice-storage-panel.tsx src/app/lexicon/voice-import/page.tsx src/app/lexicon/db-inspector/page.tsx --max-warnings=0`
- `pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts --project=chromium`

**Step 3: Confirm outputs and summarize gaps**
- Record exactly what passed.
- Record anything not run.

**Step 4: Commit docs/status if needed**
```bash
git add docs/status/project-status.md tools/lexicon/README.md tools/lexicon/OPERATOR_GUIDE.md
git commit -m "docs(lexicon): update import and voice admin status"
```
