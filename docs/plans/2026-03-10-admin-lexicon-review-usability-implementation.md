# Admin Lexicon Review Usability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the salvaged admin lexicon review usability work into one integrated, reviewable PR from current `main`.

**Architecture:** Port the salvaged review-detail slice onto a fresh branch from `main`, keeping the backend review API, admin frontend review page, and targeted smoke coverage aligned around a single reviewer-facing payload. Preserve compatibility with existing staged review items and avoid unrelated lexicon pipeline or schema changes.

**Tech Stack:** FastAPI backend, Next.js admin frontend, Vitest/Jest-style frontend tests, Pytest backend tests, Playwright smoke tests, GitHub Actions CI.

---

### Task 1: Capture and verify the salvage scope

**Files:**
- Inspect: `admin-frontend/src/app/lexicon/page.tsx`
- Inspect: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Inspect: `admin-frontend/src/lib/lexicon-reviews-client.ts`
- Inspect: `backend/app/api/lexicon_reviews.py`
- Inspect: `backend/tests/test_lexicon_reviews_api.py`
- Inspect: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`

**Step 1: Diff salvage branch against main**

Run: `git diff --stat main...feat_admin_lexicon_review_usability_salvage_20260310`

**Step 2: Record exact intended scope**
- Keep only reviewer-facing API/UI/test changes.
- Exclude unrelated docs, pipeline, DB, or auth changes.

**Step 3: Confirm preserved backup branch is no longer needed**
- Fresh salvage branch/worktree already exists as safety backup.

### Task 2: Port the salvaged change onto the fresh feature branch

**Files:**
- Modify: `admin-frontend/src/app/lexicon/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/lexicon-reviews-client.ts`
- Modify: `backend/app/api/lexicon_reviews.py`
- Modify: `backend/tests/test_lexicon_reviews_api.py`
- Modify: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`

**Step 1: Apply the salvaged diff**

Run: `git cherry-pick d0453b7` or manually port file-by-file if conflicts are clearer.

**Step 2: Reconcile drift with current main**
- Preserve current route/auth patterns on backend.
- Preserve current admin app structure and API client usage.
- Keep smoke selectors/URLs compatible with current Docker test stack.

**Step 3: Make the review payload readable and stable**
- Expose selected source, selected synset IDs, and candidate entry detail.
- Keep graceful fallback behavior for legacy candidate metadata.

### Task 3: Tighten tests first where drift appears

**Files:**
- Modify: `backend/tests/test_lexicon_reviews_api.py`
- Modify: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Modify: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`

**Step 1: Update backend tests to express intended response contract**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_reviews_api.py -q`

**Step 2: Update admin frontend tests to express intended review detail rendering**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/__tests__/page.test.tsx`

**Step 3: Update smoke test to cover the operator flow through the UI**
- Keep it focused on import/review/publish-preview/publish behavior already supported by current stack.

### Task 4: Implement compatibility and UI polish fixes

**Files:**
- Modify: `backend/app/api/lexicon_reviews.py`
- Modify: `admin-frontend/src/lib/lexicon-reviews-client.ts`
- Modify: `admin-frontend/src/app/lexicon/page.tsx`

**Step 1: Normalize staged review payloads**
- Accept current richer metadata and older `label` / `gloss`-only forms.

**Step 2: Render reviewer-readable details**
- Show selected senses, selected source, candidate lists, glosses, and reason context cleanly.
- Avoid dumping unreadable raw JSON blobs as the primary review surface.

**Step 3: Preserve security and auth posture**
- Keep admin-only access checks unchanged.
- Avoid leaking internal-only fields beyond current admin review needs.

### Task 5: Verify targeted suites and CI-relevant commands

**Files:**
- Verify: `backend/tests/test_lexicon_reviews_api.py`
- Verify: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Verify: `admin-frontend` lint/build
- Verify: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`
- Modify: `docs/status/project-status.md`

**Step 1: Run backend verification**

Run: `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_reviews_api.py -q`

**Step 2: Run admin frontend verification**

Run:
- `npm --prefix admin-frontend test -- --runInBand`
- `npm --prefix admin-frontend run lint`
- `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build`

**Step 3: Run targeted smoke verification**
- Boot the Docker test stack needed for backend, frontend, admin frontend, and Playwright.
- Run only `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`.

**Step 4: Update live status**
- Add a row to `docs/status/project-status.md` with exact evidence.

### Task 6: Commit, PR, merge, and clean up

**Files:**
- Modify: `docs/status/project-status.md`
- Verify: branch, PR, merge, cleanup state

**Step 1: Commit focused changes**

Run: `git add ... && git commit -m "feat: improve admin lexicon review usability"`

**Step 2: Push and open PR**

Run: `git push -u origin feat_admin_lexicon_review_usability_20260310` and create a PR with summary + test plan.

**Step 3: Watch checks and merge once green**
- Resolve any CI drift if needed.

**Step 4: Clean local/remote resources**
- Remove merged feature branch/worktree.
- Leave only `main` plus any intentionally preserved non-merged work.
