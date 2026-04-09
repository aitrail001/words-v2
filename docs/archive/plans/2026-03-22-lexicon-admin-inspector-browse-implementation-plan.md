# Lexicon Admin Inspector Browse Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify path guidance across review/import pages, make DB Inspector browseable for words/phrases/references, and add compiled-review batch deletion from the review DB.

**Architecture:** Extract one shared frontend path-guidance component, add a dedicated lexicon-inspector backend/API layer for browse/detail contracts, and extend compiled-review APIs with a delete-batch operation that only affects review staging tables. Keep family-specific detail rendering while using a shared browse summary contract.

**Tech Stack:** Next.js app router, React client components, FastAPI, SQLAlchemy async ORM, Jest + Testing Library, pytest, Playwright smoke.

---

### Task 1: Add failing tests for shared path guidance and compiled batch delete

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`

**Step 1: Write failing frontend assertions**

Cover:
- all three pages show the same canonical path examples
- Compiled Review shows the DB-backed note
- JSONL Review shows the file-backed note
- Import DB shows the `approved.jsonl` import note
- Compiled Review exposes a delete-batch action with confirmation

**Step 2: Write failing backend tests for batch deletion**

Cover:
- deleting an existing batch removes it and its review items
- deleting a missing batch returns `404`

**Step 3: Run focused tests and confirm failure**

### Task 2: Implement shared path guidance component

**Files:**
- Create: `admin-frontend/src/components/lexicon/path-guidance-card.tsx`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`

**Step 1: Extract a reusable component**

Include:
- canonical path examples
- reviewed directory contract
- a short page-specific note prop

**Step 2: Replace duplicated inline path copy**

Render the shared component in:
- Compiled Review
- JSONL Review
- Import DB

**Step 3: Re-run the page tests**

### Task 3: Add compiled-review batch deletion API and UI

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Modify: `admin-frontend/src/lib/lexicon-compiled-reviews-client.ts`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`

**Step 1: Add backend delete endpoint**

Add:
- `DELETE /api/lexicon-compiled-reviews/batches/{batch_id}`

Delete only review staging rows tied to the batch.

**Step 2: Add client helper**

Add a typed `deleteLexiconCompiledReviewBatch(batchId)` helper.

**Step 3: Add UI control**

Add:
- `Delete Batch` action
- confirmation prompt
- local refresh after delete

**Step 4: Re-run focused backend/frontend tests**

### Task 4: Add browseable multi-family DB Inspector backend

**Files:**
- Create or modify: `backend/app/api/lexicon_inspector.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_lexicon_inspector_api.py`

**Step 1: Add browse endpoint**

Implement:
- `GET /api/lexicon-inspector/entries`

Support:
- `family`
- `q`
- `sort`
- `limit`
- `offset`

**Step 2: Add family-aware detail endpoint(s)**

Implement either:
- one unified detail endpoint, or
- one route that dispatches by family

Return enough detail for:
- word
- phrase
- reference

**Step 3: Write and run backend tests**

Cover:
- browse default
- family filter
- query filter
- pagination
- detail per family

### Task 5: Add browseable multi-family DB Inspector UI

**Files:**
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Create or modify: `admin-frontend/src/lib/lexicon-inspector-client.ts`
- Create or modify: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`

**Step 1: Replace search-only flow with browse + inspect**

Add:
- family filter
- sort control
- browse list loaded by default
- pagination controls

**Step 2: Keep the two-pane layout**

Left:
- browse/search/filter list

Right:
- selected detail

**Step 3: Render family-specific detail sections**

Support:
- word detail
- phrase detail
- reference detail

**Step 4: Run frontend tests**

### Task 6: Update E2E smoke coverage

**Files:**
- Modify: `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`
- Create or modify: `e2e/tests/smoke/admin-db-inspector-flow.smoke.spec.ts`

**Step 1: Extend compiled-review smoke**

Cover:
- delete batch flow

**Step 2: Add inspector smoke**

Cover:
- browse entries
- filter family
- inspect one detail row

### Task 7: Verify, document, and commit

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run verification**

Run:
- focused backend tests
- focused frontend tests
- frontend lint/build
- targeted Playwright smokes
- `git diff --check`

**Step 2: Update status board**

Record:
- shared path guidance
- browseable multi-family DB Inspector
- compiled review batch deletion
- verification evidence

**Step 3: Commit cleanly**
