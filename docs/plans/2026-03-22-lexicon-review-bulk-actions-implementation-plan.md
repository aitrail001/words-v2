# Lexicon Review Bulk Actions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove per-item confirmation friction, add confirmed bulk snapshot actions for both review modes, align JSONL Review layout with Compiled Review, fix queue/count behavior, and widen raw JSON panels.

**Architecture:** Keep review pages as client-side shells, but add explicit bulk-update endpoints or bulk-update helpers at the review boundary so whole-snapshot actions are deterministic and testable. Use shared frontend review patterns between Compiled Review and JSONL Review rather than maintaining separate interaction models.

**Tech Stack:** Next.js app router, React client components, backend FastAPI review endpoints, Jest + Testing Library, Playwright smoke tests.

---

### Task 1: Add failing tests for the missing workflow behavior

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py`

**Step 1: Write failing frontend tests**

Cover:
- per-item approve/reject/reopen fire immediately with no extra confirm step
- bulk approve/reject/reopen exists and requires confirmation
- JSONL Review has only one output-directory control block
- counts update after row changes
- selection advances to the next queue item after a row action

**Step 2: Write failing backend tests for bulk operations**

Cover:
- whole compiled batch can be set to approved/rejected/pending
- whole JSONL session can be set to approved/rejected/pending
- counts returned by the page-load data reflect the updated state

**Step 3: Run focused tests and confirm failure**

### Task 2: Add backend bulk review operations

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Modify: `backend/app/api/lexicon_jsonl_reviews.py`
- Modify if needed: `backend/app/services/lexicon_jsonl_reviews.py`
- Modify: `admin-frontend/src/lib/lexicon-compiled-reviews-client.ts`
- Modify: `admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts`

**Step 1: Add minimal bulk action endpoints**

Add one bulk endpoint per review mode that can apply:
- `approved`
- `rejected`
- `pending`

Scope:
- compiled review: whole selected batch
- JSONL review: whole loaded review session

**Step 2: Keep response shape simple**

Return:
- updated counts
- enough data for the page to refresh deterministically

### Task 3: Align the review pages and fix interaction behavior

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`

**Step 1: Remove per-item confirmation**

Approve/reject/reopen on a selected row should act immediately.

**Step 2: Add bulk controls with confirmation**

Add snapshot/batch-wide:
- Approve all
- Reject all
- Reopen all

These should require confirmation before firing.

**Step 3: Align JSONL Review top layout**

Make JSONL Review match Compiled Review from:
- page header
- action strip
- decision summary cards
- search/filter controls
- batch/list layout through the detailed item list

**Step 4: Fix queue progression and count updates**

After per-item actions:
- move to the next queue item deterministically
- refresh pending/approved/rejected counts immediately

**Step 5: Remove duplicate output-directory UI**

Ensure JSONL Review exposes one authoritative output-dir control only.

**Step 6: Widen raw JSON panels**

For both review pages:
- widen the raw JSON display area
- preserve readability and scrolling

### Task 4: Update browser smoke coverage

**Files:**
- Modify: `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`
- Modify: `e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts`

**Step 1: Cover new interaction model**

Update smokes for:
- immediate per-item actions
- bulk action confirmation flows
- queue advance
- count updates

### Task 5: Verify, document, and commit

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
- bulk snapshot actions
- JSONL/compiled layout parity
- count/queue fixes
- verification evidence

**Step 3: Commit cleanly**
