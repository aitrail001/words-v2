# Import DB Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add early validation, configurable conflict/error import modes, safer phrase upserts, and clearer admin import job UX for both word and phrase imports.

**Architecture:** Extend the import request contract with explicit operator modes, add a preflight validation phase ahead of import execution, harden phrase upsert graph replacement under no-autoflush, and update the admin UI to present options and accurate failed-before-first-row messaging. Keep the existing lexicon job model where possible, using richer result payloads instead of inventing a new workflow system.

**Tech Stack:** Python lexicon tools, FastAPI backend, Celery jobs, SQLAlchemy ORM, Next.js admin frontend, pytest, Jest, Playwright.

---

### Task 1: Add failing backend/tool tests for import modes and phrase rerun safety

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `backend/tests/test_lexicon_jobs_api.py`

**Step 1: Write failing tests for preflight validation and mode handling**
- Add a test where a phrase row has an empty localized `usage_note` and assert dry-run/import reports the validation error before row mutation counts advance.
- Add a test where `error_mode="continue"` returns completed-with-errors style payload with failed row counts.
- Add a test where `conflict_mode="skip"` skips an existing word or phrase.
- Add a test where phrase rerun with `conflict_mode="upsert"` on an existing phrase succeeds without duplicate order-index failure.

**Step 2: Run the focused backend/tool tests to verify they fail**
Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: FAIL in the new tests because preflight and safe phrase upsert behavior do not exist yet.

**Step 3: Add a failing backend job/API contract test**
- Add a test for import job creation/result payload that includes the new request options and verifies failed-before-first-row jobs expose error details clearly.

**Step 4: Run the backend API test to verify it fails**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
Expected: FAIL because the API/job contract does not yet support the new fields.

**Step 5: Commit**
```bash
git add tools/lexicon/tests/test_import_db.py backend/tests/test_lexicon_jobs_api.py
git commit -m "test(lexicon): cover import hardening modes"
```

### Task 2: Implement import preflight validation and execution modes

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/README.md`

**Step 1: Add minimal implementation for shared import options**
- Extend import entry points to accept `conflict_mode`, `error_mode`, and `dry_run`.
- Validate allowed values.

**Step 2: Implement preflight validation helper**
- Add a validation pass that scans all rows and accumulates row-level validation errors before DB writes.
- Reuse existing contract validation where possible rather than duplicating rules.

**Step 3: Implement continue/fail-fast execution behavior**
- In `error_mode="continue"`, accumulate per-row failures and keep processing.
- In `error_mode="fail_fast"`, raise on first execution error.
- Return structured summary payload including failed row counts and sample errors.

**Step 4: Implement dry-run behavior**
- Ensure dry-run uses preflight and import planning logic without committing writes.
- Ensure dry-run surfaces the same content/contract issues as apply mode.

**Step 5: Run focused tool tests and make them pass**
Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: PASS

**Step 6: Update operator docs for the new import options**
- Document the mode flags and dry-run semantics in the README.

**Step 7: Commit**
```bash
git add tools/lexicon/import_db.py tools/lexicon/cli.py tools/lexicon/README.md tools/lexicon/tests/test_import_db.py
git commit -m "feat(lexicon): add import preflight and execution modes"
```

### Task 3: Harden phrase upsert graph replacement

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write or refine the failing rerun/upsert test if needed**
- Make the test specifically assert no duplicate `(phrase_entry_id, order_index)` violation on rerun.

**Step 2: Implement safe phrase graph replacement**
- Wrap phrase child rebuild in `session.no_autoflush`.
- Clear/delete existing phrase sense/example/localization graph before adding replacements.
- Preserve deterministic ordering.

**Step 3: Run the focused rerun tests**
Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -k phrase -q`
Expected: PASS

**Step 4: Commit**
```bash
git add tools/lexicon/import_db.py tools/lexicon/tests/test_import_db.py
git commit -m "fix(lexicon): make phrase import upserts rerun-safe"
```

### Task 4: Extend backend job API and task handling for import options and richer failure payloads

**Files:**
- Modify: `backend/app/api/lexicon_jobs.py`
- Modify: `backend/app/tasks/lexicon_jobs.py`
- Modify: `backend/tests/test_lexicon_jobs_api.py`

**Step 1: Add request payload support for the new import options**
- Accept and persist `conflict_mode`, `error_mode`, and `dry_run` for import-db jobs.

**Step 2: Pass options into lexicon tool execution**
- Update the Celery import job task to pass the new parameters to `run_import_file()`.

**Step 3: Preserve richer result payloads for UI**
- Ensure the job result/error payload exposes validation summary, failed row count, and sample errors.

**Step 4: Run focused backend API tests**
Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/api/lexicon_jobs.py backend/app/tasks/lexicon_jobs.py backend/tests/test_lexicon_jobs_api.py
git commit -m "feat(api): support configurable lexicon import modes"
```

### Task 5: Update admin import UI for options and accurate failed-before-first-row messaging

**Files:**
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/lib/lexicon-jobs-client.ts`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

**Step 1: Write failing UI tests**
- Add tests that assert the page submits conflict/error/dry-run options.
- Add a test that a failed zero-progress job shows `Failed before first row` and error text rather than `Waiting for first row...`.

**Step 2: Run the frontend tests to verify failure**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: FAIL until UI implementation is added.

**Step 3: Implement the UI changes**
- Add import option controls.
- Submit the new payload fields.
- Render improved status copy and completion summaries.

**Step 4: Run the frontend tests to verify pass**
Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
Expected: PASS

**Step 5: Run focused lint**
Run: `pnpm --dir admin-frontend exec eslint src/app/lexicon/import-db/page.tsx src/lib/lexicon-jobs-client.ts src/app/lexicon/import-db/__tests__/page.test.tsx --max-warnings=0`
Expected: PASS

**Step 6: Commit**
```bash
git add admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/lib/lexicon-jobs-client.ts admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx
git commit -m "feat(admin): expose lexicon import modes and failure summaries"
```

### Task 6: Add targeted end-to-end and documentation verification

**Files:**
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`
- Modify: `docs/status/project-status.md`
- Modify: `docs/plans/2026-03-30-import-db-hardening-design.md`
- Modify: `docs/plans/2026-03-30-import-db-hardening.md`

**Step 1: Add or update a smoke test for import options/status UX**
- Cover at least one dry-run or failed-early rendering path in the admin UI.

**Step 2: Run targeted e2e smoke**
Run: `E2E_API_URL=http://localhost:8000/api E2E_ADMIN_URL=http://localhost:3001 E2E_BASE_URL=http://localhost:3000 E2E_DB_PASSWORD=change_this_password_in_production pnpm --dir e2e exec playwright test tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts --project=chromium`
Expected: PASS

**Step 3: Update project status with evidence**
- Record the feature and exact verification commands/results.

**Step 4: Run final scoped verification**
Run:
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_jobs_api.py -q`
- `pnpm --dir admin-frontend test -- --runInBand lexicon/import-db`
- `pnpm --dir admin-frontend exec eslint src/app/lexicon/import-db/page.tsx src/lib/lexicon-jobs-client.ts src/app/lexicon/import-db/__tests__/page.test.tsx --max-warnings=0`
Expected: PASS

**Step 5: Commit**
```bash
git add e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts docs/status/project-status.md docs/plans/2026-03-30-import-db-hardening-design.md docs/plans/2026-03-30-import-db-hardening.md
git commit -m "test(docs): verify lexicon import hardening"
```
