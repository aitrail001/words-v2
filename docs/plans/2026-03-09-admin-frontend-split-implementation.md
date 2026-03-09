# Admin Frontend Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the lexicon admin portal out of the user-facing Next app into a separate `admin-frontend` app/container while keeping the backend and lexicon CLI tool in their current backend/tools ownership.

**Architecture:** Keep a single backend/API service and a single repo, but introduce a second Next.js app for admin-only workflows. Move the lexicon review portal to `admin-frontend`, remove admin routing/navigation from the user app, and update Docker/CORS/dev wiring so learner and admin surfaces run independently.

**Tech Stack:** Next.js 15, React 19, Jest, ESLint, Docker Compose, FastAPI backend.

---

### Task 1: Scaffold `admin-frontend`

**Files:**
- Create: `admin-frontend/` app/config files copied and trimmed from `frontend/`
- Create: `admin-frontend/package.json`
- Create: `admin-frontend/Dockerfile`
- Create: `admin-frontend/src/app/layout.tsx`
- Create: `admin-frontend/src/app/page.tsx`
- Create: `admin-frontend/src/app/login/page.tsx`

**Step 1: Write the failing test**
- Add a minimal page test asserting the admin app root renders and links to lexicon admin.

**Step 2: Run test to verify it fails**
- Run: `npm --prefix admin-frontend test -- --runInBand src/app/__tests__/page.test.tsx`

**Step 3: Write minimal implementation**
- Create admin app config and minimal pages/layout/auth plumbing.

**Step 4: Run test to verify it passes**
- Run the same command and expect PASS.

### Task 2: Move lexicon portal into `admin-frontend`

**Files:**
- Create: `admin-frontend/src/app/lexicon/page.tsx`
- Create: `admin-frontend/src/lib/lexicon-reviews-client.ts`
- Create: `admin-frontend/src/lib/words-client.ts`
- Create: `admin-frontend/src/lib/api-client.ts`
- Create: `admin-frontend/src/lib/auth-session.ts`
- Create: `admin-frontend/src/lib/auth-redirect.ts`
- Create: `admin-frontend/src/lib/auth-route-guard.ts`
- Create: `admin-frontend/src/lib/auth-nav.tsx`
- Create tests under `admin-frontend/src/app/lexicon/__tests__/` and `admin-frontend/src/lib/__tests__/`

**Step 1: Write the failing tests**
- Add the current portal tests in the new admin app.

**Step 2: Run tests to verify they fail**
- Run the new admin app lexicon test suite.

**Step 3: Write minimal implementation**
- Move/copy the verified portal implementation and supporting clients into `admin-frontend`.

**Step 4: Run tests to verify they pass**
- Run the admin app test suite.

### Task 3: Remove admin UI from user frontend

**Files:**
- Delete: `frontend/src/app/admin/lexicon/page.tsx`
- Delete: `frontend/src/app/admin/lexicon/__tests__/page.test.tsx`
- Modify: `frontend/src/lib/auth-nav.tsx`
- Modify: `frontend/src/lib/auth-route-guard.ts`
- Modify: `frontend/src/middleware.ts`
- Modify: `frontend/src/app/__tests__/layout-auth-nav.test.tsx`
- Modify: `frontend/src/app/__tests__/page.test.tsx`

**Step 1: Write/update failing tests**
- Update user frontend tests to assert there is no admin link/route guard.

**Step 2: Run tests to verify they fail**
- Run focused user frontend tests.

**Step 3: Write minimal implementation**
- Remove admin route, nav link, and `/admin/*` protection from the learner app.

**Step 4: Run tests to verify they pass**
- Re-run focused user frontend tests.

### Task 4: Update Docker/dev wiring

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/core/config.py` if needed
- Modify: docs that mention frontend/admin entrypoints

**Step 1: Write failing expectations**
- Add/update docs/tests where practical for separate admin service assumptions.

**Step 2: Implement**
- Add `admin-frontend` service on port `3001`
- Keep user frontend on `3000`
- Ensure backend allowed origins include `http://localhost:3001` and `http://admin-frontend:3000`

**Step 3: Verify**
- Run lint/tests for both apps and inspect compose config.

### Task 5: Documentation and status

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: any docs that still say the admin portal is inside the user app

**Step 1: Update docs**
- Make the split explicit and keep lexicon tool ownership on backend/tools.

**Step 2: Verify**
- Record exact test/lint evidence.
