# Lexicon Admin Workflow Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `Lexicon Ops` the primary lexicon workflow hub, keep standalone review/import/inspect pages, and move the old staged selection-review flow under a dedicated legacy route.

**Architecture:** Split the current mixed `/lexicon` page into dedicated route surfaces, add a new admin import API/page for final `import-db` operations, and connect everything from `Lexicon Ops` via snapshot-prefilled launch actions. Preserve compiled-review and JSONL-review as independent tools while making the operator flow coherent.

**Tech Stack:** Next.js admin frontend, FastAPI backend, existing lexicon import utilities in `tools/lexicon/import_db.py`, Jest, pytest, Playwright.

---

### Task 1: Add failing frontend tests for the new route structure

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Create: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Create: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`
- Create: `admin-frontend/src/app/lexicon/legacy/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/__tests__/auth-nav.test.tsx` or equivalent nav test file if present

**Step 1: Write failing tests**

Add tests that expect:

- Lexicon Ops renders launch actions for:
  - compiled review
  - JSONL review
  - import DB
  - DB inspector
- launch actions include snapshot-prefilled query parameters
- standalone Import DB page exists and renders dry-run/import controls
- standalone DB Inspector page exists and renders final DB inspection UI
- Legacy page exists and labels the staged selection review as deprecated
- nav shows the new route set instead of treating `/lexicon` as the main workflow

**Step 2: Run the targeted frontend tests to verify RED**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/ops/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/legacy/__tests__/page.test.tsx
```

Expected: failures for missing routes/components/links.

### Task 2: Add failing backend tests for admin final import endpoints

**Files:**
- Create: `backend/tests/test_lexicon_imports_api.py`

**Step 1: Write failing tests**

Cover:

- dry-run accepts a safe artifact path and returns counts
- import run accepts a safe artifact path and returns import summary
- unsafe path is rejected
- missing artifact is rejected

**Step 2: Run the backend tests to verify RED**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py -q
```

Expected: failures because the endpoint/router does not exist yet.

### Task 3: Implement backend import API and safe path handling

**Files:**
- Create: `backend/app/api/lexicon_imports.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/lexicon_ops.py` if snapshot response needs launch metadata
- Reuse: `tools/lexicon/import_db.py`

**Step 1: Implement dry-run and run endpoints**

Add:

- request models for input path, source reference, language
- safe path resolution limited to repo root and snapshot root
- dry-run using `load_compiled_rows()` + `summarize_compiled_rows()`
- actual run using `run_import_file()`

**Step 2: Keep the API admin-only and explicit**

- require admin auth
- return concise flat response payloads
- keep dry-run and actual import as separate endpoints

**Step 3: Run backend tests to verify GREEN**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py -q
```

Expected: pass.

### Task 4: Refactor the legacy mixed lexicon page into dedicated route surfaces

**Files:**
- Create: `admin-frontend/src/app/lexicon/legacy/page.tsx`
- Create: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Create: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/page.tsx`
- Optionally create shared components under `admin-frontend/src/components/lexicon/`

**Step 1: Move legacy staged review UI into `/lexicon/legacy`**

- preserve existing selection-review functionality
- add deprecated/legacy framing

**Step 2: Extract DB inspector into `/lexicon/db-inspector`**

- reuse current DB inspector behavior from the mixed page
- label it as final DB verification

**Step 3: Add `/lexicon/import-db` page**

- direct artifact path entry
- source reference/language inputs
- dry-run action
- import action
- result summary

**Step 4: Make `/lexicon` a lightweight lexicon workflow landing page**

- link operators to:
  - Lexicon Ops
  - Compiled Review
  - JSONL Review
  - Import DB
  - DB Inspector
  - Legacy

**Step 5: Run targeted frontend tests**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/__tests__/page.test.tsx src/app/lexicon/legacy/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: pass.

### Task 5: Turn Lexicon Ops into the workflow hub

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts` if needed

**Step 1: Add snapshot actions**

Add buttons/links for the selected snapshot:

- open compiled review
- open JSONL review
- open import DB
- open DB inspector

Prefill query parameters based on selected snapshot artifact paths.

**Step 2: Add embedded final-import panel**

- show default artifact path from selected snapshot
- allow override
- call dry-run/import endpoints
- show result summary inline

**Step 3: Run targeted frontend tests**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/ops/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: pass.

### Task 6: Add query-prefill support to standalone review/import pages

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify related page tests

**Step 1: Read optional query parameters on mount**

Support prefilled values for:

- snapshot
- artifact path
- decisions path
- output directory
- source reference

**Step 2: Preserve standalone behavior**

- manual entry still works without query parameters

**Step 3: Run the relevant frontend tests**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: pass.

### Task 7: Update navigation and admin home entrypoints

**Files:**
- Modify: `admin-frontend/src/lib/auth-nav.tsx`
- Modify: `admin-frontend/src/app/page.tsx`

**Step 1: Update nav labels and links**

- make `Lexicon Ops` the primary lexicon workflow link
- add `Import DB`
- add `DB Inspector`
- add `Legacy`

**Step 2: Update admin home copy**

- describe the modern compiled-review/import workflow
- stop presenting the legacy page as the main lexicon tool

**Step 3: Run nav/home tests if present**

Run the smallest relevant Jest set.

### Task 8: Add Playwright end-to-end coverage for the streamlined workflow

**Files:**
- Modify or create:
  - `e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts`
  - `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`
  - new smoke for Lexicon Ops -> Import DB if needed

**Step 1: Add snapshot-first coverage**

Cover:

- open Lexicon Ops
- choose snapshot
- launch JSONL Review or Compiled Review with prefilled values
- run Import DB dry-run from the new flow

**Step 2: Run targeted Playwright smokes**

Run the existing admin smoke set plus the new import smoke.

Expected: pass.

### Task 9: Update docs and live status

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `tools/lexicon/docs/batch.md`

**Step 1: Update operator workflow docs**

- show Lexicon Ops as the hub
- document standalone pages
- document Import DB admin flow
- mark selection review as legacy

**Step 2: Update project status with evidence**

- route changes
- backend import API
- verification results

### Task 10: Full verification before commit/PR

**Files:**
- Verify all touched surfaces

**Step 1: Run backend verification**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

**Step 2: Run frontend verification**

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/legacy/__tests__/page.test.tsx
npm --prefix admin-frontend run lint
NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

**Step 3: Run Playwright smoke verification**

Use the Docker test stack and run the targeted admin smoke tests for:

- compiled review
- JSONL review
- Lexicon Ops / Import DB

**Step 4: Run Python compile and diff hygiene**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m py_compile backend/app/api/lexicon_imports.py backend/app/api/lexicon_ops.py backend/app/main.py
git diff --check
```

**Step 5: Commit**

Commit the route cleanup and admin workflow integration in focused commits.
