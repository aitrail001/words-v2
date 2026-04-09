# Lexicon Admin Workflow Streamlining Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `Lexicon Ops` the canonical workflow shell for the admin lexicon process, make `Compiled Review` the default review branch, surface CLI-only steps explicitly, and keep standalone pages usable with consistent snapshot/artifact context.

**Architecture:** Extend the snapshot API to derive workflow-stage metadata and preferred artifacts, revise the admin IA so `Lexicon Ops` shows stage/next-step/outside-portal guidance, add compiled-review import-by-path for snapshot-first operation, and make standalone review/import/inspect pages workflow-aware without removing manual entry modes.

**Tech Stack:** Next.js admin frontend, FastAPI backend, SQLAlchemy review models, existing lexicon import/review services in `backend/app/api/*` and `tools/lexicon/*`, Jest, pytest, Playwright.

---

### Task 1: Add failing backend tests for workflow metadata on snapshot responses

**Files:**
- Modify: `backend/tests/test_lexicon_ops_api.py`
- Inspect: `backend/app/api/lexicon_ops.py`

**Step 1: Write the failing test**

Add tests that expect `/api/lexicon-ops/snapshots` and `/api/lexicon-ops/snapshots/{snapshot}` to return derived workflow metadata such as:

- `workflow_stage`
- `recommended_action`
- `preferred_review_artifact_path`
- `preferred_import_artifact_path`
- `outside_portal_steps`

Cover at least:

- snapshot with only base artifacts
- snapshot with compiled artifact but no `approved.jsonl`
- snapshot with `approved.jsonl`

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_ops_api.py -q
```

Expected: FAIL because these fields do not exist yet.

**Step 3: Commit**

```bash
git add backend/tests/test_lexicon_ops_api.py
git commit -m "test(admin): cover lexicon ops workflow metadata"
```

### Task 2: Implement workflow metadata in `lexicon_ops`

**Files:**
- Modify: `backend/app/api/lexicon_ops.py`
- Test: `backend/tests/test_lexicon_ops_api.py`

**Step 1: Add response fields**

Extend the snapshot summary/detail response models with:

- workflow stage
- recommended next action
- preferred compiled artifact
- preferred import artifact
- outside-portal step summary

**Step 2: Implement derived-stage logic**

Derive stage based on artifact presence. Keep logic explicit and deterministic.

**Step 3: Include family-aware compiled artifacts**

Account for:

- `words.enriched.jsonl`
- `phrases.enriched.jsonl`
- `references.enriched.jsonl`
- `approved.jsonl`

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_ops_api.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/lexicon_ops.py backend/tests/test_lexicon_ops_api.py
git commit -m "feat(admin): add lexicon ops workflow metadata"
```

### Task 3: Add failing backend tests for compiled-review import by path

**Files:**
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Inspect: `backend/app/api/lexicon_compiled_reviews.py`

**Step 1: Write the failing test**

Add tests for a new admin-only import-by-path route or request mode that:

- accepts a safe compiled artifact path from an existing snapshot
- imports rows into compiled-review staging without file upload
- rejects unsafe paths
- preserves source reference and artifact-family behavior

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py -q
```

Expected: FAIL because import-by-path does not exist yet.

**Step 3: Commit**

```bash
git add backend/tests/test_lexicon_compiled_reviews_api.py
git commit -m "test(admin): cover compiled review import by path"
```

### Task 4: Implement compiled-review import by path

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Reuse: `backend/app/services/lexicon_jsonl_reviews.py` path resolution helpers where appropriate
- Test: `backend/tests/test_lexicon_compiled_reviews_api.py`

**Step 1: Add request model and endpoint or route mode**

Support importing an existing compiled artifact by safe path, not only by upload.

**Step 2: Reuse safe path discipline**

Restrict resolution to repo/snapshot-safe roots. Do not shell out.

**Step 3: Reuse the existing compiled-review persistence path**

The import-by-path route should call the same validation, hashing, row parsing, and batch/item creation logic as upload-driven import.

**Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/lexicon_compiled_reviews.py backend/tests/test_lexicon_compiled_reviews_api.py
git commit -m "feat(admin): add compiled review import by path"
```

### Task 5: Add failing frontend tests for workflow shell and stage rail

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Inspect: `admin-frontend/src/app/lexicon/ops/page.tsx`

**Step 1: Write the failing test**

Expect `Lexicon Ops` to render:

- stage rail
- current stage label
- recommended next action
- alternate review action
- outside-portal steps section
- artifact classification or preferred artifact details

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: FAIL because the workflow shell UI is not present yet.

**Step 3: Commit**

```bash
git add admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx
git commit -m "test(admin): cover lexicon ops workflow shell"
```

### Task 6: Implement the `Lexicon Ops` workflow shell

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts`
- Test: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`

**Step 1: Add stage rail and workflow summary**

Render:

- stage rail
- current stage
- recommended next action
- alternate action

**Step 2: Add explicit outside-portal panel**

Show CLI-only steps with readiness and artifact expectations based on API metadata.

**Step 3: Improve snapshot action semantics**

Use preferred artifact data from the API to drive:

- `Open Compiled Review`
- `Open JSONL Review`
- `Open Import DB`
- `Open DB Inspector`

**Step 4: Preserve embedded Import DB panel**

Keep the import panel in `Ops`, but align it with preferred import artifact selection and explicit stage language.

**Step 5: Run test to verify it passes**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: PASS.

**Step 6: Commit**

```bash
git add admin-frontend/src/app/lexicon/ops/page.tsx admin-frontend/src/lib/lexicon-ops-client.ts admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx
git commit -m "feat(admin): turn lexicon ops into workflow shell"
```

### Task 7: Add failing frontend tests for snapshot-context headers on standalone pages

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`

**Step 1: Write the failing test**

Expect each page to render:

- stage label
- snapshot or source reference context when provided
- active artifact/input context
- next-step guidance

**Step 2: Run tests to verify they fail**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx
```

Expected: FAIL because those headers are not present yet.

**Step 3: Commit**

```bash
git add admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx
git commit -m "test(admin): cover lexicon workflow context headers"
```

### Task 8: Implement workflow-aware standalone pages

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Modify related tests

**Step 1: Add shared workflow context header pattern**

Each page should show:

- stage name
- snapshot/source reference
- active artifact or input path
- next step after this page

**Step 2: Compiled Review**

Add path-driven import option or path-prefill behavior when launched from `Ops`.

**Step 3: JSONL Review**

Keep existing manual path mode, but show snapshot/artifact context and workflow placement.

**Step 4: Import DB**

Show this as the canonical final DB write step and surface approved artifact provenance if present.

**Step 5: DB Inspector**

Frame as post-import verification only.

**Step 6: Run tests to verify they pass**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx
```

Expected: PASS.

**Step 7: Commit**

```bash
git add admin-frontend/src/app/lexicon/compiled-review/page.tsx admin-frontend/src/app/lexicon/jsonl-review/page.tsx admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/app/lexicon/db-inspector/page.tsx admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx
git commit -m "feat(admin): add workflow-aware lexicon stage pages"
```

### Task 9: Demote legacy in navigation and home IA

**Files:**
- Modify: `admin-frontend/src/lib/auth-nav.tsx`
- Modify: `admin-frontend/src/app/page.tsx`
- Modify related nav/home tests if present

**Step 1: Update primary lexicon nav**

Make `Lexicon Ops` the primary lexicon entrypoint. Visually demote `Legacy`.

**Step 2: Update admin home copy**

Describe:

- `Lexicon Ops` as the workflow shell
- `Compiled Review` as default review mode
- `JSONL Review` as alternate

**Step 3: Run relevant tests**

Run the smallest Jest set that covers layout/nav/home behavior.

**Step 4: Commit**

```bash
git add admin-frontend/src/lib/auth-nav.tsx admin-frontend/src/app/page.tsx
git commit -m "feat(admin): align lexicon nav with workflow shell"
```

### Task 10: Update operator docs and status board

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `tools/lexicon/docs/batch.md`
- Modify: `docs/status/project-status.md`
- Optionally add: `docs/plans/2026-03-22-lexicon-admin-workflow-streamlining-design.md`

**Step 1: Align terminology**

Use the same workflow language across admin UI and operator docs:

- snapshot
- compiled review
- approved export/materialize
- import DB
- verify DB
- outside-portal steps

**Step 2: Update status board**

Record the workflow-shell change with verification evidence.

**Step 3: Commit**

```bash
git add tools/lexicon/OPERATOR_GUIDE.md tools/lexicon/docs/batch.md docs/status/project-status.md
git commit -m "docs(lexicon): align admin workflow and operator docs"
```

### Task 11: Run verification for backend and frontend

**Files:**
- No code changes required

**Step 1: Run backend targeted suite**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_ops_api.py backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_imports_api.py backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

Expected: PASS.

**Step 2: Run frontend targeted suite**

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/ops/__tests__/page.test.tsx src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/legacy/__tests__/page.test.tsx src/app/__tests__/layout-auth-nav.test.tsx src/app/__tests__/page.test.tsx
```

Expected: PASS.

**Step 3: Run frontend lint/build**

```bash
npm --prefix admin-frontend run lint
NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

Expected: PASS.

**Step 4: Run backend compile check**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m py_compile backend/app/api/lexicon_ops.py backend/app/api/lexicon_compiled_reviews.py backend/app/api/lexicon_imports.py
```

Expected: PASS.

### Task 12: Add and run Playwright workflow smoke

**Files:**
- Modify or create:
  - `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`
  - `e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts`
  - `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`

**Step 1: Add coverage for the streamlined workflow**

Cover:

- `Ops` shows current stage and next action
- `Ops -> Compiled Review` carries snapshot context
- `Ops -> JSONL Review` carries artifact context
- `Ops -> Import DB` prefills approved artifact
- `Ops -> DB Inspector` remains reachable as final verification

**Step 2: Run targeted Playwright smoke**

Run the existing admin smoke set for this workflow.

Expected: PASS.

**Step 3: Commit**

```bash
git add e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts
git commit -m "test(e2e): cover streamlined lexicon admin workflow"
```

### Task 13: Final review, code review, and branch finish

**Files:**
- No new code required

**Step 1: Run final diff hygiene**

```bash
git diff --check
git status --short
```

Expected: clean diff and intentional changes only.

**Step 2: Request code review**

Use the repository review workflow before merge.

**Step 3: Prepare PR**

Summarize:

- workflow shell in `Lexicon Ops`
- default compiled-review branch
- explicit outside-portal guidance
- snapshot-context headers across lexicon pages
- compiled-review import-by-path

**Step 4: Merge and clean branch**

After CI passes, merge and remove the feature worktree/branch.
