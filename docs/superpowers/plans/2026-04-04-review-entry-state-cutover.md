# Review Entry State Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove legacy learner review queue compatibility, make `EntryReviewState` the sole learner review state, and fix the broken `Learn now -> submit -> continue` flow.

**Architecture:** Keep the existing learner review endpoints, but route their behavior through persisted `EntryReviewState` rows only. Start with failing regression tests for the real learn-now flow, then remove legacy fallback branches and make `learning/start` durably persist the returned ids before any follow-up request.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Next.js, Playwright, pytest

---

## File Structure

- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`
- Modify: `backend/tests/test_review_api.py`
- Modify: `backend/tests/test_review_service.py`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`
- Modify: `docs/status/project-status.md`

### Task 1: Add failing backend regression coverage for learn-now submit

**Files:**
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Add a service-level regression test for `start_learning_entry` and immediate submit**

Write a test that:

- creates a word with at least one meaning
- calls `start_learning_entry`
- captures the returned `queue_item_id`
- calls `submit_queue_review` with that id
- expects success instead of `Queue item ... not found`

- [ ] **Step 2: Run the targeted backend test and verify it fails for the right reason**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py -k "learning and submit" -q
```

Expected:

- fail because the current learner review flow does not durably support the returned id path

- [ ] **Step 3: Add an API-level regression test for `learning/start -> queue submit`**

Write a test that:

- authenticates a user
- posts to `/api/reviews/entry/word/{id}/learning/start`
- uses the returned `queue_item_id`
- posts to `/api/reviews/queue/{id}/submit`
- asserts `200`

- [ ] **Step 4: Run the targeted API test and verify it fails before the fix**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_api.py -k "learning start" -q
```

Expected:

- fail before the implementation change

### Task 2: Remove legacy learner review queue compatibility

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`
- Modify: `backend/app/api/reviews.py`

- [ ] **Step 1: Remove legacy queue branching from learner review lookup and submit paths**

Update the review service so learner queue read and submit behavior resolves through `EntryReviewState` only.

- [ ] **Step 2: Make `learning/start` durably persist returned state ids**

Ensure `start_learning_entry` commits or otherwise durably persists new `EntryReviewState` rows before returning the response payload.

- [ ] **Step 3: Keep existing API shapes but return `EntryReviewState`-backed payloads only**

Retain the current endpoint contracts for this slice, but remove hidden fallback behavior to `ReviewCard` where it affects learner review.

- [ ] **Step 4: Run the targeted backend tests and verify they pass**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k "learning or queue" -q
```

Expected:

- targeted learner review tests pass

### Task 3: Add a browser regression test for the real learn-now path

**Files:**
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`

- [ ] **Step 1: Extend browser coverage to start from learner entry detail**

Update or add a smoke test that:

1. opens a learner word detail page
2. clicks `Learn now`
3. answers the first prompt or taps `Show meaning`
4. continues successfully
5. asserts no runtime not-found error appears

- [ ] **Step 2: Keep a focused frontend unit test for the single-model path**

Adjust mocked review-page tests so they assume `queue_item_id` always refers to an `EntryReviewState` row and no legacy queue fallback exists.

- [ ] **Step 3: Run targeted frontend and E2E checks**

Run:

```bash
npm --prefix frontend test -- --runInBand src/app/review/__tests__/page.test.tsx
```

Run:

```bash
pnpm --dir e2e test -- tests/smoke/user-review-submit.smoke.spec.ts --project=chromium
```

Expected:

- frontend review tests pass
- smoke review regression passes

### Task 4: Document the status change with evidence

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a status-log entry for the learner review cutover**

Record:

- legacy learner review compatibility removed
- `Learn now -> submit -> continue` regression fixed
- exact verification commands and outcomes

- [ ] **Step 2: Re-run the final targeted verification set**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k "learning or queue" -q
```

Run:

```bash
npm --prefix frontend test -- --runInBand src/app/review/__tests__/page.test.tsx
```

Run:

```bash
pnpm --dir e2e test -- tests/smoke/user-review-submit.smoke.spec.ts --project=chromium
```

Expected:

- all targeted verification commands pass
