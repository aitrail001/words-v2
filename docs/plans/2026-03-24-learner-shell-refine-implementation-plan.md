# Learner Shell Refine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refine the learner app shell to add standalone search/settings tabs, separate word/phrase detail routes, global plus local translation toggles, denser knowledge-map range tiles, and screenshot-aligned detail cleanup.

**Architecture:** Keep the existing learner API surface and dashboard/map/list structure, but move navigation into a persistent learner tab shell and split the old `/knowledge/[entryType]/[entryId]` detail page into standalone `/word/[id]` and `/phrase/[id]` routes backed by a shared detail component. Extend learner preferences with a persisted translation-visibility default and enrich learner detail payloads with confusable words and relation grouping inputs so the new detail UI can stay data-driven.

**Tech Stack:** Next.js App Router, React client components, TypeScript, FastAPI, SQLAlchemy, Alembic, Jest, Playwright.

---

### Task 1: Add the persisted global translation-visibility preference

**Files:**
- Create: `backend/alembic/versions/017_add_user_preference_translation_visibility.py`
- Modify: `backend/app/models/user_preference.py`
- Modify: `backend/app/api/user_preferences.py`
- Modify: `backend/tests/test_user_preferences_api.py`
- Modify: `frontend/src/lib/user-preferences-client.ts`

**Step 1: Write the failing backend tests**

- Add tests asserting:
  - default response includes `show_translations_by_default: true`
  - `PUT /api/user-preferences` accepts and persists `show_translations_by_default`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_user_preferences_api.py -q`

Expected: FAIL because the field does not exist yet.

**Step 3: Write minimal backend implementation**

- Add the boolean column and defaults to `UserPreference`
- update API request/response models and persistence logic
- add Alembic migration `017_add_user_preference_translation_visibility.py`

**Step 4: Write the failing frontend client test if needed**

- If there is client coverage for preferences, extend it to require the new field shape.

**Step 5: Run targeted tests to verify they pass**

Run:
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_user_preferences_api.py -q`

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/alembic/versions/017_add_user_preference_translation_visibility.py backend/app/models/user_preference.py backend/app/api/user_preferences.py backend/tests/test_user_preferences_api.py frontend/src/lib/user-preferences-client.ts
git commit -m "feat(learner): persist translation visibility preference"
```

### Task 2: Extend learner detail payload for confusable words and relation rendering

**Files:**
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `frontend/src/lib/knowledge-map-client.ts`

**Step 1: Write the failing API tests**

- Add tests asserting learner detail for a word can return:
  - accent-aware pronunciation
  - confusable words
  - relation metadata sufficient for grouped chips/sections

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: FAIL because the learner detail response shape is incomplete.

**Step 3: Write minimal implementation**

- extend the learner detail response models
- map `word.confusable_words`
- keep accent-aware pronunciation selection on the learner detail payload
- preserve existing phrase behavior unchanged

**Step 4: Update the frontend client types**

- extend `KnowledgeMapEntryDetail` with the new fields

**Step 5: Run targeted tests to verify they pass**

Run:
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: PASS.

**Step 6: Commit**

```bash
git add backend/app/api/knowledge_map.py backend/app/services/knowledge_map.py backend/tests/test_knowledge_map_api.py frontend/src/lib/knowledge-map-client.ts
git commit -m "feat(learner): enrich detail payload for standalone entry pages"
```

### Task 3: Build the shared learner shell and bottom tab navigation

**Files:**
- Create: `frontend/src/components/learner-shell-nav.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/__tests__/page.test.tsx`

**Step 1: Write the failing frontend tests**

- Add assertions for persistent learner tab navigation on learner pages:
  - `Home`
  - `Knowledge`
  - `Search`
  - `Settings`

**Step 2: Run test to verify it fails**

Run: `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/__tests__/page.test.tsx`

Expected: FAIL because the shell nav does not exist.

**Step 3: Write minimal implementation**

- add a learner bottom-nav component
- place it in the learner layout flow without breaking auth navigation
- keep admin routing untouched

**Step 4: Run targeted tests to verify they pass**

Run: `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/__tests__/page.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/learner-shell-nav.tsx frontend/src/app/layout.tsx frontend/src/app/__tests__/page.test.tsx
git commit -m "feat(learner): add persistent learner tab navigation"
```

### Task 4: Move detail routes to `/word/[id]` and `/phrase/[id]`

**Files:**
- Create: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Create: `frontend/src/app/word/[entryId]/page.tsx`
- Create: `frontend/src/app/phrase/[entryId]/page.tsx`
- Create: `frontend/src/app/word/[entryId]/__tests__/page.test.tsx`
- Create: `frontend/src/app/phrase/[entryId]/__tests__/page.test.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/knowledge-map/page.tsx`
- Modify: `frontend/src/app/knowledge-list/[status]/page.tsx`
- Delete or deprecate: `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx`

**Step 1: Write the failing route/component tests**

- assert learner detail pages resolve under `/word/[id]` and `/phrase/[id]`
- assert dashboard/map/list links target the new routes

**Step 2: Run test to verify it fails**

Run:
- `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/__tests__/page.test.tsx src/app/knowledge-map/__tests__/page.test.tsx 'src/app/knowledge-list/[status]/__tests__/page.test.tsx'`

Expected: FAIL because links still target `/knowledge/...`.

**Step 3: Write minimal implementation**

- introduce a shared detail component
- create word and phrase route wrappers
- update learner link generation everywhere
- remove the old route or replace it with a redirect if needed during transition

**Step 4: Run targeted tests to verify they pass**

Run the same Jest commands plus the new route tests.

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/app/word/[entryId]/page.tsx frontend/src/app/phrase/[entryId]/page.tsx frontend/src/app/word/[entryId]/__tests__/page.test.tsx frontend/src/app/phrase/[entryId]/__tests__/page.test.tsx frontend/src/app/page.tsx frontend/src/app/knowledge-map/page.tsx frontend/src/app/knowledge-list/[status]/page.tsx
git commit -m "refactor(learner): move entry detail to standalone word and phrase routes"
```

### Task 5: Implement the standalone search tab and remove embedded search

**Files:**
- Create: `frontend/src/app/search/page.tsx`
- Create: `frontend/src/app/search/__tests__/page.test.tsx`
- Modify: `frontend/src/app/knowledge-map/page.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts` only if route helpers are needed

**Step 1: Write the failing search page tests**

- assert `/search` renders history first
- assert typing shows results
- assert clicking a result navigates to `/word/[id]` or `/phrase/[id]`
- assert knowledge map and detail pages no longer render embedded search panels

**Step 2: Run test to verify it fails**

Run:
- `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/search/__tests__/page.test.tsx src/app/knowledge-map/__tests__/page.test.tsx 'src/app/word/[entryId]/__tests__/page.test.tsx'`

Expected: FAIL.

**Step 3: Write minimal implementation**

- build the standalone search page
- remove embedded search UI from map/detail
- keep existing search-history/search endpoints

**Step 4: Run targeted tests to verify they pass**

Run the same Jest commands.

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/app/search/page.tsx frontend/src/app/search/__tests__/page.test.tsx frontend/src/app/knowledge-map/page.tsx frontend/src/components/knowledge-entry-detail-page.tsx
git commit -m "feat(learner): add standalone search tab"
```

### Task 6: Refine the entry detail UI

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/word/[entryId]/__tests__/page.test.tsx`
- Modify: `frontend/src/app/phrase/[entryId]/__tests__/page.test.tsx`

**Step 1: Write the failing detail tests**

- assert there is no previous/next entry navigation
- assert multi-meaning navigation appears when there are multiple meanings/senses
- assert local translation toggle can hide/show translations
- assert relation/confusable sections render when provided
- assert pronunciation reflects the returned learner detail value

**Step 2: Run test to verify it fails**

Run:
- `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand 'src/app/word/[entryId]/__tests__/page.test.tsx' 'src/app/phrase/[entryId]/__tests__/page.test.tsx'`

Expected: FAIL.

**Step 3: Write minimal implementation**

- fix hero/card layering
- add meaning/sense pager controls
- wire the local translation toggle using the persisted global default as initial state
- render grouped relation chips and confusable words

**Step 4: Run targeted tests to verify they pass**

Run the same Jest commands.

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/app/globals.css frontend/src/app/word/[entryId]/__tests__/page.test.tsx frontend/src/app/phrase/[entryId]/__tests__/page.test.tsx
git commit -m "feat(learner): refine standalone detail cards"
```

### Task 7: Tighten knowledge-map density and update settings UI

**Files:**
- Modify: `frontend/src/app/knowledge-map/page.tsx`
- Modify: `frontend/src/app/settings/page.tsx`
- Modify: `frontend/src/app/knowledge-map/__tests__/page.test.tsx`
- Modify: `frontend/src/app/settings/__tests__/page.test.tsx`

**Step 1: Write the failing tests**

- assert the bottom range strip uses denser tile layout
- assert settings exposes the new global translation default control
- assert settings is reachable from the learner bottom nav

**Step 2: Run test to verify it fails**

Run:
- `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/knowledge-map/__tests__/page.test.tsx src/app/settings/__tests__/page.test.tsx`

Expected: FAIL.

**Step 3: Write minimal implementation**

- shrink bottom range tiles and increase columns
- update settings UI to include the global translation default
- keep accent, locale, and view controls intact

**Step 4: Run targeted tests to verify they pass**

Run the same Jest commands.

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/app/knowledge-map/page.tsx frontend/src/app/settings/page.tsx frontend/src/app/knowledge-map/__tests__/page.test.tsx frontend/src/app/settings/__tests__/page.test.tsx
git commit -m "feat(learner): tighten map density and add translation setting"
```

### Task 8: Verify end to end and update status docs

**Files:**
- Modify: `e2e/tests/smoke/knowledge-map.smoke.spec.ts`
- Modify: `e2e/tests/smoke/auth-guard.smoke.spec.ts` if route assertions change
- Modify: `docs/status/project-status.md`

**Step 1: Write or update the failing smoke coverage**

- cover:
  - bottom nav to `Search` and `Settings`
  - search -> result -> standalone detail
  - detail translation toggle
  - knowledge map still reachable and usable

**Step 2: Run smoke to verify it fails before final fixes if needed**

Run:
- `docker compose -f docker-compose.yml exec -T playwright sh -lc "cd /workspace/e2e && E2E_BASE_URL=http://frontend:3000 E2E_API_URL=http://backend:8000/api E2E_ADMIN_URL=http://admin-frontend:3001 E2E_DB_URL=postgresql://vocabapp:devpassword@postgres:5432/vocabapp_dev npx playwright test tests/smoke/knowledge-map.smoke.spec.ts --grep @smoke --max-failures=1 --project=chromium"`

**Step 3: Run full verification**

Run:
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_user_preferences_api.py backend/tests/test_knowledge_map_api.py -q`
- `NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand src/app/__tests__/page.test.tsx src/app/knowledge-map/__tests__/page.test.tsx 'src/app/knowledge-list/[status]/__tests__/page.test.tsx' src/app/settings/__tests__/page.test.tsx src/app/search/__tests__/page.test.tsx 'src/app/word/[entryId]/__tests__/page.test.tsx' 'src/app/phrase/[entryId]/__tests__/page.test.tsx'`
- `npm --prefix frontend run lint`
- `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix frontend run build`
- targeted Playwright smoke command above

**Step 4: Update status board**

- add one concise `2026-03-24` entry to `docs/status/project-status.md` with fresh evidence

**Step 5: Commit**

```bash
git add e2e/tests/smoke/knowledge-map.smoke.spec.ts e2e/tests/smoke/auth-guard.smoke.spec.ts docs/status/project-status.md
git commit -m "test(learner): cover standalone search and detail shell"
```
