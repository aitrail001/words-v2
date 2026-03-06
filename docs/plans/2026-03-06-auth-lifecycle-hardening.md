# Auth Lifecycle Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Status:** COMPLETED  
**Date:** 2026-03-06  
**Goal:** Harden authentication lifecycle end-to-end by adding backend refresh/logout with token lifecycle controls, frontend protected-route/session handling, and auth-focused smoke verification.

**Architecture:** Implement short-lived access tokens plus rotating refresh tokens backed by Redis state (hashed refresh token records and access-token revocation by `jti`). On the frontend, enforce protected-route redirects, perform deterministic session recovery on unauthorized responses, and expose explicit logout UX. Add focused backend/frontend/E2E tests first (RED), then implement minimum code to pass (GREEN), then run full verification.

**Tech Stack:** FastAPI, SQLAlchemy, Redis, PyJWT, Next.js App Router, Jest, Playwright, Docker Compose, GitHub Actions CI.

---

## Design Alignment (Brief)

1. Token contract:
- Access token carries `sub`, `token_type=access`, `jti`, `exp`.
- Refresh token carries `sub`, `token_type=refresh`, `jti`, `exp`.
- Refresh endpoint rotates refresh token and returns a new pair.
- Logout revokes current access token and submitted refresh token.

2. Frontend auth behavior:
- Unauthenticated access to protected routes redirects to `/login`.
- API 401 handling: attempt refresh once; if refresh fails, clear token and redirect to `/login`.
- Authenticated nav shows `Logout`; logout clears local token and calls backend logout.

3. Test scope:
- Backend unit/integration tests for refresh/logout/rotation/revocation.
- Frontend unit tests for token lifecycle and guard behavior.
- E2E smoke tests for auth contract and route guarding in PR-required suite.

---

### Task 1: Backend Token Lifecycle Tests (RED)

**Files:**
- Modify: `backend/tests/test_security.py`
- Modify: `backend/tests/test_auth.py`
- Create: `backend/tests/test_auth_tokens.py`

**Step 1: Add failing token-claims tests**
- Add tests asserting access/refresh token claim shape includes `token_type` and `jti`.
- Add tests asserting decode helper enforces expected token type and expiry behavior.

**Step 2: Add failing auth API lifecycle tests**
- Add tests for `POST /api/auth/refresh` success and rotation semantics.
- Add tests for rejection when refresh endpoint receives access token.
- Add tests for logout revocation behavior and malformed `sub` handling (`401`, not `500`).

**Step 3: Add failing token-service tests**
- Add tests for refresh token hash storage TTL, rotation invalidation, reuse rejection, and access token revocation checks.

**Step 4: Run focused backend tests to confirm RED**
- Run: `docker compose -f docker-compose.test.yml run --rm test pytest backend/tests/test_security.py backend/tests/test_auth.py backend/tests/test_auth_tokens.py -q`
- Expected: failures specific to missing refresh/logout/token lifecycle implementation.

---

### Task 2: Backend Refresh/Logout Implementation (GREEN)

**Files:**
- Modify: `backend/app/core/security.py`
- Create: `backend/app/services/auth_tokens.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/config.py` (only if new config knobs are required)

**Step 1: Implement token primitives**
- Add helper(s) to mint access/refresh tokens with `token_type` and `jti`.
- Add decode helper with expected token-type validation.

**Step 2: Implement Redis-backed auth token service**
- Store hashed refresh-token state with TTL.
- Rotate refresh tokens atomically and invalidate prior token.
- Revoke/check access-token `jti` until token expiry.

**Step 3: Implement API contract**
- Update register/login responses to include token pair.
- Add `POST /api/auth/refresh` and `POST /api/auth/logout`.
- Harden `get_current_user` UUID parse path to return `401` for malformed subjects.

**Step 4: Run backend lifecycle tests to confirm GREEN**
- Run: `docker compose -f docker-compose.test.yml run --rm test pytest backend/tests/test_security.py backend/tests/test_auth.py backend/tests/test_auth_tokens.py -q`
- Expected: all pass.

---

### Task 3: Frontend Auth Lifecycle Tests (RED)

**Files:**
- Create: `frontend/src/lib/__tests__/api-client.auth-lifecycle.test.ts`
- Modify: `frontend/src/app/__tests__/page.test.tsx`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Create: `frontend/src/app/__tests__/layout-auth-nav.test.tsx`

**Step 1: Add failing API client lifecycle tests**
- Assert token persistence/clear behavior and auth header attachment.
- Assert unauthorized response triggers refresh attempt and fallback clear+redirect behavior.

**Step 2: Add failing protected-route/navigation tests**
- Assert unauthenticated access to protected route flows to `/login`.
- Assert authenticated state preserves access.
- Assert logout action clears auth state and navigation updates.

**Step 3: Run focused frontend tests to confirm RED**
- Run: `npm --prefix frontend test -- --runInBand src/lib/__tests__/api-client.auth-lifecycle.test.ts src/app/__tests__/layout-auth-nav.test.tsx src/app/__tests__/page.test.tsx src/app/review/__tests__/page.test.tsx`
- Expected: failures tied to missing lifecycle handling and guards.

---

### Task 4: Frontend Protected Route + Refresh/Logout Handling (GREEN)

**Files:**
- Modify: `frontend/src/lib/api-client.ts`
- Create: `frontend/src/middleware.ts` (or equivalent route-guard mechanism)
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/login/page.tsx` and/or `frontend/src/app/register/page.tsx` (if token-pair handling requires updates)

**Step 1: Implement API client lifecycle**
- Integrate refresh-on-401 (single retry guard).
- Clear token and redirect to `/login` when refresh fails.
- Add logout method that calls backend logout and clears local token.

**Step 2: Implement route protection**
- Guard protected routes (minimum: `/` and `/review`) with redirect to `/login` when unauthenticated.

**Step 3: Implement logout UX**
- Show logout action when authenticated.
- Invoke logout flow and route users back to `/login`.

**Step 4: Run frontend lifecycle tests to confirm GREEN**
- Run: `npm --prefix frontend test -- --runInBand`
- Run: `npm --prefix frontend run lint`

---

### Task 5: E2E Smoke Auth Coverage + CI-Relevant Verification

**Files:**
- Create: `e2e/tests/smoke/auth-contract.smoke.spec.ts`
- Create: `e2e/tests/smoke/auth-guard.smoke.spec.ts`
- Modify: `e2e/tests/helpers/auth.ts` (if helper additions are needed)
- Modify: `.github/workflows/ci.yml` (only if smoke discovery needs adjustment)

**Step 1: Add failing smoke tests**
- Add auth contract smoke assertions for unauthenticated `401` and authenticated `/auth/me` success.
- Add protected-route redirect smoke assertion.

**Step 2: Run smoke tests to confirm RED/GREEN progression**
- Run: `npm --prefix e2e run test:smoke`

**Step 3: Full verification evidence**
- Run: `docker compose -f docker-compose.test.yml run --rm test pytest -q`
- Run: `npm --prefix frontend run lint`
- Run: `npm --prefix frontend test -- --runInBand`
- Run: `npm --prefix e2e run test:smoke`
- Optional (if runtime allows): `npm --prefix e2e run test:full`

---

### Task 6: Status Documentation Update

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update workstream row**
- Move auth lifecycle reality/evidence to reflect refresh/logout/protected-route hardening progress.

**Step 2: Update top gaps and milestone**
- Promote next unresolved gap after auth slice completion.

**Step 3: Append status log with evidence**
- Add date-stamped entry including executed command evidence.

---

## Execution Notes

1. Keep scope tight to auth lifecycle hardening only (no unrelated refactors).
2. Use subagents for independent backend/frontend/e2e slices, then run unified verification in controller session.
3. Do not claim completion until fresh command outputs confirm all required checks.

---

## Completion Note (2026-03-06)

- Implemented backend refresh/logout lifecycle with typed JWT claims, Redis-backed refresh rotation, and access-token revocation checks.
- Implemented frontend protected-route middleware, auth-aware nav/logout UX, and 401 recovery with refresh-token rotation handling.
- Added auth-focused smoke coverage (`auth-contract`, `auth-guard`) and helper support for middleware-authenticated browser sessions.
- Updated canonical status board with evidence and next gaps.

Verification evidence (fresh runs):
- `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` → `113 passed`
- `npm --prefix frontend run lint` → pass
- `npm --prefix frontend test -- --runInBand` → `7 suites / 26 tests passed`
- `docker compose -f docker-compose.yml --profile tests exec -T playwright ... npm run test:smoke:ci` → `6 passed`
- `docker compose -f docker-compose.yml --profile tests exec -T playwright ... npm run test:full` → `7 passed`
