# Review Entry State Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify learner review onto `EntryReviewState` and one post-answer state machine so correct answers go to the normal detail page, failed answers go through guided relearn, and review sessions advance deterministically.

**Architecture:** Keep the current learner-review entry points, but remove legacy learner-review runtime behavior and route all queue/session logic through `EntryReviewState` plus explicit review-session state. Reuse the normal detail page for successful answers and the existing learning-pass presentation for failed answers, with deterministic session advancement after each branch.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Next.js, React Testing Library, pytest, Playwright

---

## File Structure

- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `frontend/src/app/review/page.tsx`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
- Modify: `frontend/src/lib/review-session-storage.ts`
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`
- Modify: `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`
- Modify: `scripts/seed_review_scenarios.py`
- Modify: `docs/status/project-status.md`

### Task 1: Lock the backend session contract with failing tests

**Files:**
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Add a failing service test for the correct-answer confirmation contract**

Write a test that:

- creates a due `EntryReviewState`
- submits a correct answer
- asserts the item is not yet finalized/advanced until a separate continuation step is invoked
- asserts the chosen schedule can still be adjusted before advancement

- [ ] **Step 2: Run the targeted service test and confirm it fails for the missing confirmation boundary**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py -k "correct and continue" -q`

Expected: FAIL because the current flow advances or persists too early.

- [ ] **Step 3: Add a failing service test for the failed-answer relearn contract**

Write a test that:

- creates two due `EntryReviewState` rows
- submits a wrong answer or `Show meaning` for the first item
- asserts failure scheduling is algorithm-selected automatically
- asserts the failed item is not returned again in the same session
- asserts the next pending item becomes active after relearn completion

- [ ] **Step 4: Add an API regression test for correct-answer detail confirmation and failed-answer guided relearn**

Write API tests that:

- hit the review submit endpoint for a correct answer and assert the response enters the success-detail state
- hit the review submit endpoint for a failed answer and assert the response enters the relearn state with no schedule override controls
- assert session advancement happens only on the correct continuation action or relearn completion action

- [ ] **Step 5: Run the targeted backend tests and confirm the new expectations fail before implementation**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k "continue or relearn or show_meaning" -q`

Expected: FAIL on the old handoff behavior.

### Task 2: Remove legacy learner-review runtime behavior and encode the new state machine

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`
- Modify: `backend/app/api/reviews.py`

- [ ] **Step 1: Remove any remaining learner-review read/submit fallback to legacy review models**

Ensure learner queue lookup, due queue generation, and submit behavior resolve through `EntryReviewState` only.

- [ ] **Step 2: Add explicit session-state transitions for success confirmation and relearn completion**

Implement a backend contract that distinguishes:

- active prompt
- pending success confirmation on detail page
- guided relearn in progress
- next queue advancement

- [ ] **Step 3: Make correct answers defer final advancement until `Continue review`**

Keep the chosen next-review timing mutable until the user confirms on the detail page.

- [ ] **Step 4: Make wrong answers and `Show meaning` fail immediately, schedule automatically, and enter relearn**

No schedule override should be exposed or required in this branch.

- [ ] **Step 5: Advance to the next queue item after relearn completion without re-asking the failed item**

Preserve review history while preventing same-session immediate retry.

- [ ] **Step 6: Run the targeted backend verification and confirm it passes**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k "continue or relearn or queue" -q`

Expected: PASS for the updated review contract.

### Task 3: Reuse the normal detail page for successful answers

**Files:**
- Modify: `frontend/src/app/review/page.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/lib/review-session-storage.ts`
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

- [ ] **Step 1: Add failing frontend tests for the unified success handoff**

Write tests that assert:

- a correct answer from any prompt family transitions to the normal detail page
- entry audio auto-plays on the success detail page
- the page does not advance until `Continue review` is clicked

- [ ] **Step 2: Add failing frontend tests for the unified failed handoff**

Write tests that assert:

- wrong answer or `Show meaning` transitions to the guided relearn flow
- no next-review dropdown is shown in that flow
- relearn completion advances to the next queue item

- [ ] **Step 3: Replace inline reveal-card success handling with the detail-page confirmation flow**

Use the existing detail component rather than a separate review-only success surface.

- [ ] **Step 4: Keep review progress visible only inside the review shell**

Ensure the home page still shows only due count while `/review` shows `Review x / y`.

- [ ] **Step 5: Run the targeted frontend tests**

Run: `npm --prefix frontend test -- --runInBand src/app/review/__tests__/page.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

### Task 4: Reuse the learning pass for failed-review relearn

**Files:**
- Modify: `frontend/src/app/review/page.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`

- [ ] **Step 1: Add failing tests that model relearn as a true learning pass**

Cover:

- stepping through all definitions/examples
- auto-play behavior
- explicit `Next` progression
- advancement to the next queue item after the final relearn step

- [ ] **Step 2: Implement a relearn mode that reuses the current learn-now presentation**

Do not invent a separate one-off failed-review UI if the existing learning pass can be reused.

- [ ] **Step 3: Verify the failed item is not immediately retried**

Assert this in backend and frontend tests.

- [ ] **Step 4: Run the targeted mixed verification set**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k "relearn or learning" -q`

Run: `npm --prefix frontend test -- --runInBand src/app/review/__tests__/page.test.tsx`

Expected: PASS.

### Task 5: Seed deterministic manual and CI scenarios for every prompt family

**Files:**
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
- Modify: `scripts/seed_review_scenarios.py`
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`
- Modify: `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`

- [ ] **Step 1: Align the DB seeders with the canonical queue-state contract**

Ensure seeded scenarios create:

- persisted `EntryReviewState` rows only
- deterministic prompt-family ordering
- enough words/phrases to cover manual testing of all review types

- [ ] **Step 2: Add or update E2E tests for success and failed paths across prompt families**

Cover:

- multiple choice
- audio
- fill-in / sentence gap
- typed recall
- phrase review

- [ ] **Step 3: Make the browser tests assert the canonical handoff rules instead of prompt-family-specific branches**

Each family should now have the same success and failure structure.

- [ ] **Step 4: Run the targeted Playwright suite**

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/smoke/user-review-submit.smoke.spec.ts tests/smoke/user-review-prompt-families.smoke.spec.ts --project=chromium`

Expected: PASS.

### Task 6: Update status and final verification evidence

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Record the new canonical review contract**

Update project status with:

- success path behavior
- failed / relearn behavior
- legacy learner-review removal
- manual seeding availability for prompt-family testing

- [ ] **Step 2: Run the final verification set**

Run: `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py backend/tests/test_knowledge_map_api.py -q`

Run: `npm --prefix frontend run lint`

Run: `npm --prefix frontend test -- --runInBand src/app/review/__tests__/page.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx src/app/__tests__/page.test.tsx`

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/smoke/user-review-submit.smoke.spec.ts tests/smoke/user-review-prompt-families.smoke.spec.ts --project=chromium`

Expected: PASS for all commands above.
