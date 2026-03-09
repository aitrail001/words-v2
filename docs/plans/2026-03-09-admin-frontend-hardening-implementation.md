# Admin Frontend Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the last admin-frontend hardening needed before PR by adding a real publish-path smoke, enforcing backend admin-only access on lexicon review surfaces, and extending preprod/CI validation to cover the split admin app.

**Architecture:** Keep the current split architecture: learner `frontend`, separate `admin-frontend`, shared FastAPI backend, and shared Playwright stack. Harden the operator path by (1) making the backend lexicon-review endpoints require admin role, (2) ensuring smoke/preprod stacks boot `admin-frontend`, and (3) proving one real publish-adjacent admin flow and one review-save flow through Playwright while keeping tests thin and deterministic.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js 15, Playwright, Docker Compose, GitHub Actions.

---

### Task 1: Enforce backend admin role on lexicon review APIs

**Files:**
- Modify: `backend/app/api/lexicon_reviews.py`
- Modify: `backend/app/api/auth.py` and/or existing auth dependency helpers if needed
- Test: `backend/tests/test_lexicon_reviews_api.py`

**Step 1: Write the failing tests**
- Add/adjust tests proving non-admin authenticated users receive `403` from lexicon review import/list/item-update/publish-preview/publish routes.
- Add one positive admin-role test proving the same route still works for an admin token.

**Step 2: Run test to verify it fails**
- Run: `cd backend && pytest -q tests/test_lexicon_reviews_api.py -q`
- Expected: non-admin access is currently allowed, so new assertions fail.

**Step 3: Write minimal implementation**
- Reuse the existing authenticated user dependency and add a small admin-role guard for lexicon review routes.
- Keep error shape simple and consistent: `403` with a clear detail string.

**Step 4: Run test to verify it passes**
- Re-run the focused backend review API tests.

### Task 2: Add publish-adjacent admin Playwright smoke

**Files:**
- Create/Modify: `e2e/tests/smoke/admin-review-flow.smoke.spec.ts`
- Optionally create: `e2e/tests/helpers/lexicon-review.ts`
- Modify only if needed: `admin-frontend/src/app/lexicon/page.tsx`

**Step 1: Write the failing test**
- Extend the real admin smoke to cover one additional publish-adjacent interaction with minimal brittleness.
- Prefer a stable flow such as `publish-preview` after approving the imported item, not a deep many-row publish scenario.

**Step 2: Run test to verify it fails**
- Run the targeted Playwright spec against the compose test stack.
- Expected: fail if UI/backend behavior is missing or selectors need tightening.

**Step 3: Write minimal implementation**
- Patch only the minimum needed to make the publish-preview/admin flow stable.
- Avoid broad UI refactors.

**Step 4: Run test to verify it passes**
- Re-run the targeted admin smoke, then the full smoke pack.

### Task 3: Extend preprod readiness to cover admin frontend

**Files:**
- Modify: `.github/workflows/preprod-readiness.yml`
- Modify: `docker-compose.yml` only if the workflow needs a stack adjustment not already present
- Modify: `e2e/scripts/run-local-smoke.sh` only if parity changes are needed

**Step 1: Write the failing expectation**
- Update the workflow/readiness logic so it explicitly waits for `admin-frontend` and passes `E2E_ADMIN_URL` into Playwright smoke.
- Use local YAML/config validation and the existing smoke command path as the proof target.

**Step 2: Implement**
- Boot `admin-frontend` in preprod-readiness.
- Wait for `http://localhost:3001/login`.
- Pass `E2E_ADMIN_URL=http://admin-frontend:3001` into the Playwright container run.
- Update checklist summary text so it mentions admin frontend readiness.

**Step 3: Verify**
- Run YAML parse sanity and `docker compose config`.
- If practical, run the same local smoke path that now includes admin checks.

### Task 4: Re-run verification matrix

**Files:**
- No code changes required; verification only

**Step 1: Backend focused verification**
- Run: `cd backend && pytest -q tests/test_lexicon_reviews_api.py`

**Step 2: Admin frontend verification**
- Run: `npm --prefix admin-frontend run lint`
- Run: `npm --prefix admin-frontend test -- --runInBand`
- Run: `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build`

**Step 3: Smoke verification**
- Run targeted admin smoke(s) under compose.
- Run full local smoke: `E2E_SMOKE_CLEANUP=1 ./e2e/scripts/run-local-smoke.sh`

**Step 4: Workflow/config verification**
- Run: `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); YAML.load_file(".github/workflows/preprod-readiness.yml"); puts "workflow yaml OK"'`
- Run: `docker compose -f docker-compose.yml config`

### Task 5: Update live status and prep for PR

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/plans/2026-03-08-lexicon-future-improvements-todo.md`

**Step 1: Update docs/status**
- Record admin-role enforcement, new smoke scope, and preprod/admin validation coverage with exact evidence.
- Reduce TODOs to the next real remaining gaps only.

**Step 2: Final verification recap**
- Confirm fresh command outputs are available for every completion claim.

**Step 3: Prepare PR handoff**
- Summarize changed files, verification, and any remaining follow-up items.

## Implementation Summary

- Completed the planned admin hardening slice across backend RBAC, admin-auth/runtime behavior, Playwright smoke coverage, and preprod workflow coverage.
- Kept the split architecture intact: learner `frontend`, separate `admin-frontend`, shared FastAPI backend, shared Docker/Playwright stack.
- Left broader lexicon review-gating and learner-facing schema evolution out of scope for this slice.

## Verification Evidence

- Backend targeted verification: `docker compose -f docker-compose.yml exec -T backend pytest tests/test_lexicon_reviews_api.py` (`21` passed).
- Admin frontend verification: `npm --prefix admin-frontend test -- --runInBand` (`8` suites / `28` tests passed), `npm --prefix admin-frontend run lint` (pass), and `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build` (pass).
- Targeted admin smoke: Playwright container run covering `admin-auth` and `admin-review-flow` passed.
- Full local smoke: `E2E_SMOKE_CLEANUP=1 NEXT_PUBLIC_API_URL=http://backend:8000/api ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://frontend:3000,http://admin-frontend:3001 ./e2e/scripts/run-local-smoke.sh` (`10` passed).
- Workflow/config verification: `docker compose -f docker-compose.yml --profile tests config` (pass) and YAML parse for `.github/workflows/ci.yml` + `.github/workflows/preprod-readiness.yml` (pass).

## Result

- This slice is PR-ready: runtime path, local verification, and preprod inclusion are now aligned for the split admin app.
- The next follow-up should target lexicon review-gating / publish policy and broader learner-facing schema work rather than more split-admin plumbing.

