# Learner Dashboard And Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the learner root route into the screenshot-style dashboard, move the full map to `/knowledge-map`, add filtered list and settings screens, and extend the learner API to support dashboard summary plus filtered/sorted mixed word+phrase lists.

**Architecture:** Keep the mixed learner catalog and entry-detail contracts already in place, but add one dashboard-summary endpoint and one filtered-list endpoint. On the frontend, split the current monolithic root page into dedicated route pages for dashboard, full knowledge map, filtered lists, and settings, while preserving the existing detail flow and status mutations.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js App Router, React client components, Tailwind CSS, Jest + Testing Library, Playwright

---

### Task 1: Add backend tests for learner dashboard summary

**Files:**
- Modify: `backend/tests/test_knowledge_map_api.py`

**Step 1: Write the failing test**

- Add coverage for `GET /api/knowledge-map/dashboard` asserting:
  - total counts per status
  - discovery range start/end
  - next learn entry selection

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -k dashboard -q`

Expected: FAIL because the endpoint does not exist yet.

**Step 3: Write minimal implementation**

- Modify `backend/app/api/knowledge_map.py`
- Reuse the existing catalog builder to derive status counts and next learner positions.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -k dashboard -q`

Expected: PASS

### Task 2: Add backend tests for filtered list API

**Files:**
- Modify: `backend/tests/test_knowledge_map_api.py`

**Step 1: Write the failing test**

- Add coverage for `GET /api/knowledge-map/list` asserting:
  - `status=new` maps to `undecided`
  - `status=learning`, `status=to_learn`, and `status=known` filter correctly
  - search filters results
  - sort orders by rank and alphabetic value

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -k "list and knowledge_map" -q`

Expected: FAIL because the endpoint and filtering logic do not exist yet.

**Step 3: Write minimal implementation**

- Modify `backend/app/api/knowledge_map.py`
- Add query validation and a small filtered/sorted catalog projection.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -k "list and knowledge_map" -q`

Expected: PASS

### Task 3: Extend frontend client tests for the new learner API calls

**Files:**
- Modify: `frontend/src/lib/__tests__/*` if present
- Modify: `frontend/src/lib/knowledge-map-client.ts`

**Step 1: Write the failing test**

- Add or extend client tests for:
  - `getKnowledgeMapDashboard`
  - `getKnowledgeMapList`

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand`

Expected: FAIL in the targeted client test file.

**Step 3: Write minimal implementation**

- Add TypeScript types and client functions for the new endpoints.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand`

Expected: PASS for the targeted client test file.

### Task 4: Replace the root page tests with learner dashboard expectations

**Files:**
- Modify: `frontend/src/app/__tests__/page.test.tsx`

**Step 1: Write the failing test**

- Assert the new `/` dashboard renders:
  - summary card
  - total uncovered CTA
  - `New`, `Started`, `To Learn`
  - `Discover` and `Learn`
  - `Practice with Lexi`

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/__tests__/page.test.tsx`

Expected: FAIL because the root route is still the full map.

**Step 3: Write minimal implementation**

- Replace `frontend/src/app/page.tsx` with the dashboard route.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/__tests__/page.test.tsx`

Expected: PASS

### Task 5: Add tests for the dedicated full-map route

**Files:**
- Create: `frontend/src/app/knowledge-map/__tests__/page.test.tsx`
- Create: `frontend/src/app/knowledge-map/page.tsx`

**Step 1: Write the failing test**

- Assert the moved full-map route keeps:
  - tile grid
  - cards/tags/list modes
  - current range heading

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/knowledge-map/__tests__/page.test.tsx`

Expected: FAIL because the route does not exist yet.

**Step 3: Write minimal implementation**

- Move or extract the current map page logic into `/knowledge-map`.
- Keep query-param support for focused entry/range routing if feasible in the first pass.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/knowledge-map/__tests__/page.test.tsx`

Expected: PASS

### Task 6: Add tests for filtered learner list routes

**Files:**
- Create: `frontend/src/app/knowledge-list/[status]/__tests__/page.test.tsx`
- Create: `frontend/src/app/knowledge-list/[status]/page.tsx`

**Step 1: Write the failing test**

- Assert list pages render:
  - title based on status
  - search input
  - sort button
  - mixed entry rows
  - status control

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand 'src/app/knowledge-list/[status]/__tests__/page.test.tsx'`

Expected: FAIL because the route does not exist yet.

**Step 3: Write minimal implementation**

- Build one reusable list page backed by the new filtered-list endpoint.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand 'src/app/knowledge-list/[status]/__tests__/page.test.tsx'`

Expected: PASS

### Task 7: Add tests for learner settings route

**Files:**
- Create: `frontend/src/app/settings/__tests__/page.test.tsx`
- Create: `frontend/src/app/settings/page.tsx`
- Modify: `frontend/src/lib/user-preferences-client.ts`

**Step 1: Write the failing test**

- Assert the settings page renders the screenshot sections:
  - `Learning`
  - `Translation`
  - `Review Cards`
  - `Data/Storage`
- Assert persisted fields load and save through the existing preferences API wiring.

**Step 2: Run test to verify it fails**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/settings/__tests__/page.test.tsx`

Expected: FAIL because the route does not exist yet.

**Step 3: Write minimal implementation**

- Build the settings UI.
- Persist only the fields already supported by the backend.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand src/app/settings/__tests__/page.test.tsx`

Expected: PASS

### Task 8: Update the detail page and shared navigation wiring

**Files:**
- Modify: `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx`
- Modify: `frontend/src/app/globals.css`

**Step 1: Write or update failing tests**

- Adjust detail-page tests only if route back-links or CTA destinations changed.

**Step 2: Run targeted test to verify failure**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand 'src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx'`

Expected: FAIL only if the detail route needs new nav behavior.

**Step 3: Write minimal implementation**

- Update navigation targets so the detail flow returns sensibly into the new route structure.

**Step 4: Run test to verify it passes**

Run: `./node_modules/.bin/jest --config jest.config.js --runInBand 'src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx'`

Expected: PASS

### Task 9: Add targeted learner smoke coverage for the new dashboard flows

**Files:**
- Modify: `e2e/tests/smoke/knowledge-map.smoke.spec.ts`
- Modify: `e2e/tests/helpers/knowledge-map-fixture.ts`

**Step 1: Write the failing smoke expectations**

- Cover:
  - dashboard loads
  - total uncovered opens full map
  - `New` opens filtered list
  - `Started` opens filtered list
  - `To Learn` opens filtered list
  - `Discover` opens the focused map
  - `Learn` opens the next learnable entry

**Step 2: Run targeted smoke to verify it fails**

Run: `docker compose -f docker-compose.yml exec -T playwright sh -lc "E2E_BASE_URL='http://frontend:3000' E2E_API_URL='http://backend:8000/api' E2E_ADMIN_URL='http://admin-frontend:3001' E2E_DB_URL='postgresql://vocabapp:devpassword@postgres:5432/vocabapp_dev' npx playwright test tests/smoke/knowledge-map.smoke.spec.ts --grep @smoke --max-failures=1"`

Expected: FAIL because the learner app still starts on the map route and has no filtered list/settings flow.

**Step 3: Write minimal implementation**

- Update the E2E fixture data only as needed to make dashboard summary and learn/discover navigation deterministic.

**Step 4: Run targeted smoke to verify it passes**

Run: `docker compose -f docker-compose.yml exec -T playwright sh -lc "E2E_BASE_URL='http://frontend:3000' E2E_API_URL='http://backend:8000/api' E2E_ADMIN_URL='http://admin-frontend:3001' E2E_DB_URL='postgresql://vocabapp:devpassword@postgres:5432/vocabapp_dev' npx playwright test tests/smoke/knowledge-map.smoke.spec.ts --grep @smoke --max-failures=1"`

Expected: PASS

### Task 10: Run slice verification and update live status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run backend verification**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: PASS

**Step 2: Run targeted frontend verification**

Run:

```bash
./node_modules/.bin/jest --config jest.config.js --runInBand \
  src/app/__tests__/page.test.tsx \
  src/app/knowledge-map/__tests__/page.test.tsx \
  'src/app/knowledge-list/[status]/__tests__/page.test.tsx' \
  src/app/settings/__tests__/page.test.tsx \
  'src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx'
```

Expected: PASS

**Step 3: Run lint and production build**

Run:

- `npm --prefix frontend run lint`
- `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix frontend run build`

Expected: PASS

**Step 4: Run targeted Docker smoke**

Run: `docker compose -f docker-compose.yml exec -T playwright sh -lc "E2E_BASE_URL='http://frontend:3000' E2E_API_URL='http://backend:8000/api' E2E_ADMIN_URL='http://admin-frontend:3001' E2E_DB_URL='postgresql://vocabapp:devpassword@postgres:5432/vocabapp_dev' npx playwright test tests/smoke/knowledge-map.smoke.spec.ts --grep @smoke --max-failures=1"`

Expected: PASS

**Step 5: Update live status**

- Add the learner dashboard/list/settings slice and fresh verification evidence to `docs/status/project-status.md`.

**Step 6: Final verification**

Run: `git diff --check`

Expected: PASS
