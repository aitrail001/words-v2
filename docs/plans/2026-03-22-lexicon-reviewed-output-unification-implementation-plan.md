# Lexicon Reviewed Output Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make both review modes produce and consume the same reviewed outputs under a shared `reviewed/` snapshot subdirectory, with `Lexicon Ops` and `Import DB` aligned to that contract.

**Architecture:** Keep compiled artifacts in the snapshot root and move reviewed outputs into `snapshot/reviewed/`. Add compiled-review materialization and JSONL-review downloads so both review modes support both output styles while converging on the same artifact names and locations.

**Tech Stack:** Next.js admin frontend, FastAPI backend, lexicon review materialization helpers, Jest, Playwright

---

### Task 1: Lock the unified reviewed-output contract in tests

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py`

**Step 1: Add failing expectations**

Cover:
- compiled-review materialize to `reviewed/`
- JSONL-review download actions
- Ops looking for `reviewed/approved.jsonl`
- Import DB preferring `reviewed/approved.jsonl`

**Step 2: Run the focused test slices and confirm failure**

### Task 2: Implement shared reviewed-output helpers and backend endpoints

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Modify: `backend/app/api/lexicon_jsonl_reviews.py`
- Modify: `backend/app/services/lexicon_jsonl_reviews.py`

**Step 1: Add reviewed-output path helpers**

Define a shared convention:
- `<snapshot>/reviewed/approved.jsonl`
- `<snapshot>/reviewed/review.decisions.jsonl`
- `<snapshot>/reviewed/rejected.jsonl`
- `<snapshot>/reviewed/regenerate.jsonl`

**Step 2: Add compiled-review materialize endpoint**

Write DB-backed review outputs into the reviewed directory and return the output paths/counts.

**Step 3: Add JSONL-review download endpoints**

Stream the current approved/decisions/rejected/regenerate outputs without requiring the operator to inspect the filesystem manually.

### Task 3: Update admin pages and Ops/import wiring

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/lib/lexicon-compiled-reviews-client.ts`
- Modify: `admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts`

**Step 1: Compiled Review**

- add materialize button
- default output dir to `reviewed/`
- keep downloads

**Step 2: JSONL Review**

- add download buttons for the four reviewed outputs
- default materialize dir to `reviewed/`

**Step 3: Ops and Import**

- make `Ops` prefer `reviewed/approved.jsonl`
- make `Import DB` use the same convention in placeholders/context

### Task 4: Update docs and status

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Document the unified folder contract**

Explain that reviewed outputs live under `reviewed/` regardless of review mode.

### Task 5: Verify

**Step 1: Run focused backend/frontend tests**

**Step 2: Run frontend lint/build**

**Step 3: Run focused Playwright review/ops/import smokes against the worktree stack**

**Step 4: Commit**

