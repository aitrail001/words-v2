# Import Preflight and Manual Dry Run Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove Import DB dry-run autostart and add a shared preflight/importability path used by both dry run and real import before any SQL write occurs.

**Architecture:** Keep real import as the only async write path. Add a shared preflight analysis layer in the lexicon import tool, make dry run use that layer only, and make real import run the same preflight before entering the SQL write phase. Update Ops navigation and Import DB UI so opening the page is passive and operator-driven.

**Tech Stack:** Next.js/React admin frontend, Python lexicon tools, FastAPI backend APIs, Jest, pytest, Playwright.

---

### Task 1: Remove Import DB autostart from Lexicon Ops navigation

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Test: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

**Step 1: Write the failing frontend test**

Add/adjust a test so Import DB with prefilled query params does not auto-call dry run on render.

**Step 2: Run test to verify it fails**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: FAIL because page still auto-starts dry run.

**Step 3: Write minimal implementation**

- Remove `autostart: "1"` from Lexicon Ops navigation into Import DB.
- Remove the Import DB `autoStart` logic and the `useEffect` that triggers `execute("dry-run")` on load.

**Step 4: Run test to verify it passes**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: PASS

**Step 5: Commit**

```bash
git add admin-frontend/src/app/lexicon/ops/page.tsx admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx
git commit -m "fix(admin): remove import dry-run autostart"
```

### Task 2: Add a shared preflight/importability result type

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing lexicon-tool tests**

Add tests for a structured preflight result that can report:
- row counts
- blocking errors
- error samples
- conflict/importability summary

Cover both word and phrase rows.

**Step 2: Run test to verify it fails**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: FAIL because no shared preflight API exists yet.

**Step 3: Write minimal implementation**

In `tools/lexicon/import_db.py`, add a shared internal function such as:
- `run_import_preflight(...)`

It should:
- parse/load rows
- run existing import-blocking validators
- perform conflict/importability analysis without writes
- return structured summary + `error_samples`

**Step 4: Run test to verify it passes**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/lexicon/import_db.py tools/lexicon/tests/test_import_db.py
git commit -m "feat(lexicon): add shared import preflight"
```

### Task 3: Make dry run use preflight only

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `backend/app/api/lexicon_imports.py`
- Test: `tools/lexicon/tests/test_import_db.py`
- Test: `backend/tests/test_lexicon_imports_api.py`

**Step 1: Write the failing tests**

Add tests proving:
- dry run returns preflight/importability output
- dry run does not enter the write/import phase
- dry-run API preserves numeric summary contract and separate error samples

**Step 2: Run tests to verify they fail**

Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py -q`
Expected: FAIL for missing preflight-only dry-run behavior.

**Step 3: Write minimal implementation**

- In `run_import_file(...)`, route `dry_run=True` to preflight only.
- In dry-run API, return preflight summary/errors.
- Do not touch worker/job paths for dry run.

**Step 4: Run tests to verify they pass**

Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/lexicon/import_db.py backend/app/api/lexicon_imports.py tools/lexicon/tests/test_import_db.py backend/tests/test_lexicon_imports_api.py
git commit -m "feat(api): make import dry run preflight-only"
```

### Task 4: Make real import run mandatory preflight before SQL writes

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `backend/app/tasks/lexicon_jobs.py`
- Modify: `backend/app/services/lexicon_import_jobs.py`
- Test: `tools/lexicon/tests/test_import_db.py`
- Test: `backend/tests/test_lexicon_jobs_api.py`

**Step 1: Write the failing tests**

Add tests proving:
- import runs shared preflight first
- blocking preflight errors fail before write path begins
- failed import job surfaces the preflight error clearly

**Step 2: Run tests to verify they fail**

Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
Expected: FAIL

**Step 3: Write minimal implementation**

- In real import path, call shared preflight before entering the write loop.
- If preflight returns blocking errors, raise/fail immediately.
- Preserve current worker-backed progress behavior for actual imports.

**Step 4: Run tests to verify they pass**

Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/lexicon/import_db.py backend/app/tasks/lexicon_jobs.py backend/app/services/lexicon_import_jobs.py tools/lexicon/tests/test_import_db.py backend/tests/test_lexicon_jobs_api.py
git commit -m "feat(lexicon): require import preflight before writes"
```

### Task 5: Expand preflight coverage for common import blockers

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing tests**

Add focused tests for import-blocking preflight cases across words and phrases, including but not limited to:
- invalid localized translation fields
- bad nested structure shapes
- duplicate per-parent order indexes in input
- existing-row conflict classification by `conflict_mode`

**Step 2: Run test to verify it fails**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: FAIL on new cases.

**Step 3: Write minimal implementation**

Extend the preflight layer only enough to cover these real blockers without replaying the whole ORM import path.

**Step 4: Run test to verify it passes**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tools/lexicon/import_db.py tools/lexicon/tests/test_import_db.py
git commit -m "feat(lexicon): expand import preflight coverage"
```

### Task 6: Update Import DB UI copy to reflect manual dry run and preflight behavior

**Files:**
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Test: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

**Step 1: Write the failing test**

Add/adjust UI tests to assert the page copy and behavior reflect:
- manual dry run only
- dry run as validation/importability check
- no worker progress semantics for dry run

**Step 2: Run test to verify it fails**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: FAIL

**Step 3: Write minimal implementation**

Update page copy only where needed to describe dry run accurately.

**Step 4: Run test to verify it passes**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: PASS

**Step 5: Commit**

```bash
git add admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx
git commit -m "docs(admin): clarify import preflight behavior"
```

### Task 7: Add targeted end-to-end coverage for manual dry run behavior

**Files:**
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`

**Step 1: Write the failing e2e assertion**

Add assertions that:
- opening Import DB from Ops does not auto-run dry run
- user must click `Dry Run`
- dry-run results render only after explicit operator action

**Step 2: Run test to verify it fails**

Run:
```bash
E2E_WORDS_DATA_ROOT=/Users/johnson/AI/src/words-v2/.worktrees/feat_import_preflight_and_manual_dry_run_20260330/data \
E2E_API_URL=http://localhost:8000/api \
E2E_ADMIN_URL=http://localhost:3001 \
E2E_BASE_URL=http://localhost:3000 \
E2E_DB_PASSWORD=devpassword \
pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts --project=chromium
```
Expected: FAIL until navigation/autostart behavior is removed.

**Step 3: Write minimal implementation**

Adjust only the smoke expectations/fixtures needed for the new manual flow.

**Step 4: Run test to verify it passes**

Run the same Playwright command.
Expected: PASS

**Step 5: Commit**

```bash
git add e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts
git commit -m "test(e2e): cover manual import dry run flow"
```

### Task 8: Final verification and docs/status update

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update status doc**

Add the feature state and exact verification evidence.

**Step 2: Run scoped verification**

Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jobs_api.py -q`
- `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
- `pnpm --dir admin-frontend exec eslint src/app/lexicon/import-db/page.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/ops/page.tsx --max-warnings=0`
- `E2E_WORDS_DATA_ROOT=/Users/johnson/AI/src/words-v2/.worktrees/feat_import_preflight_and_manual_dry_run_20260330/data E2E_API_URL=http://localhost:8000/api E2E_ADMIN_URL=http://localhost:3001 E2E_BASE_URL=http://localhost:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts --project=chromium`

Expected: all pass.

**Step 3: Commit**

```bash
git add docs/status/project-status.md
git commit -m "docs(status): record import preflight verification"
```
