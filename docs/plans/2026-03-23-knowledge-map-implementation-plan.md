# Knowledge Map Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a learner-facing mixed word/phrase knowledge map with persisted entry-level learner statuses, preferences, search history, range drill-in, and learner detail views.

**Architecture:** Add dedicated learner tables and APIs in the backend instead of reusing admin inspector routes. Rebuild the learner frontend around a knowledge-map flow that consumes normalized mixed-entry payloads and respects learner preferences for accent and translation locale.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Next.js App Router, React, Jest, Tailwind CSS

---

### Task 1: Add learner persistence models and migration

**Files:**
- Create: `backend/alembic/versions/013_add_learner_knowledge_map_tables.py`
- Create: `backend/app/models/learner_entry_status.py`
- Create: `backend/app/models/user_preference.py`
- Create: `backend/app/models/search_history.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_learner_knowledge_models.py`

**Step 1: Write the failing tests**

- Add model tests for defaults, unique constraints, enum-like status values, and basic relationships/fields.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_learner_knowledge_models.py -q`

**Step 3: Write minimal implementation**

- Add the three model files.
- Add the Alembic migration for the new tables and indexes.
- Export the models from `backend/app/models/__init__.py`.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_learner_knowledge_models.py -q`

**Step 5: Commit**

Commit message: `feat(db): add learner knowledge map persistence tables`

---

### Task 2: Add learner knowledge-map API contract and service layer

**Files:**
- Create: `backend/app/services/knowledge_map.py`
- Create: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_knowledge_map_api.py`

**Step 1: Write the failing tests**

- Cover:
  - overview bucketing
  - mixed word/phrase range browse
  - learner detail for word and phrase
  - status upsert
  - search and search history
  - previous/next metadata

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

**Step 3: Write minimal implementation**

- Add normalized response schemas and route handlers.
- Add service helpers to merge words and phrases into a stable learner browse list.
- Reuse current word and phrase parsing logic where practical.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

**Step 5: Commit**

Commit message: `feat(api): add learner knowledge map routes`

---

### Task 3: Add learner preferences API

**Files:**
- Create: `backend/app/api/user_preferences.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_user_preferences_api.py`

**Step 1: Write the failing tests**

- Cover defaults for users without a row.
- Cover upsert and validation for accent/view preference.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_user_preferences_api.py -q`

**Step 3: Write minimal implementation**

- Add response/update schemas.
- Add authenticated GET/PUT handlers.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_user_preferences_api.py -q`

**Step 5: Commit**

Commit message: `feat(api): add learner preferences endpoints`

---

### Task 4: Add learner frontend clients and normalized types

**Files:**
- Create: `frontend/src/lib/knowledge-map-client.ts`
- Create: `frontend/src/lib/user-preferences-client.ts`
- Test: `frontend/src/lib/__tests__/knowledge-map-client.test.ts`
- Test: `frontend/src/lib/__tests__/user-preferences-client.test.ts`

**Step 1: Write the failing tests**

- Assert endpoint paths and payload shapes for overview, range browse, detail, status update, search history, and preferences.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/lib/__tests__/knowledge-map-client.test.ts frontend/src/lib/__tests__/user-preferences-client.test.ts`

**Step 3: Write minimal implementation**

- Add typed API helpers matching the backend contracts.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/lib/__tests__/knowledge-map-client.test.ts frontend/src/lib/__tests__/user-preferences-client.test.ts`

**Step 5: Commit**

Commit message: `feat(frontend): add learner knowledge map clients`

---

### Task 5: Replace learner dashboard with overview map and range drill-in

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/__tests__/knowledge-map-page.test.tsx`
- Modify: `frontend/src/app/globals.css`
- Optionally create: `frontend/src/components/knowledge-map/*.tsx`

**Step 1: Write the failing tests**

- Cover map rendering, range selection, status legend, and view switching.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/knowledge-map-page.test.tsx`

**Step 3: Write minimal implementation**

- Render the 100-entry tiles from overview data.
- Add range drill-in with cards/tags/list view modes.
- Use status colors consistently.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/knowledge-map-page.test.tsx`

**Step 5: Commit**

Commit message: `feat(frontend): add learner knowledge map overview`

---

### Task 6: Add learner detail screen and search/history flow

**Files:**
- Create: `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx`
- Create: `frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`
- Modify: `frontend/src/app/page.tsx`

**Step 1: Write the failing tests**

- Cover word detail rendering.
- Cover phrase detail rendering.
- Cover previous/next navigation.
- Cover search history rendering and item open behavior.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 3: Write minimal implementation**

- Add a dedicated learner detail route.
- Render hero, main definition/sense carousel, examples, and status actions.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 5: Commit**

Commit message: `feat(frontend): add learner entry detail flow`

---

### Task 7: Integrate preferences into learner browse/detail behavior

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx`
- Test: `frontend/src/app/__tests__/knowledge-map-page.test.tsx`
- Test: `frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 1: Write the failing tests**

- Cover accent selection fallback.
- Cover translation-locale selection fallback.
- Cover default view preference behavior.

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/knowledge-map-page.test.tsx frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 3: Write minimal implementation**

- Fetch preferences on learner views.
- Apply the selected accent and translation locale.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/knowledge-map-page.test.tsx frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 5: Commit**

Commit message: `feat(frontend): apply learner knowledge preferences`

---

### Task 8: Update navigation, docs, and live status

**Files:**
- Modify: `frontend/src/lib/auth-nav.tsx`
- Modify: `docs/status/project-status.md`

**Step 1: Write the failing check**

- Identify the new learner workstream status text and navigation destination updates.

**Step 2: Run verification for docs/navigation expectations**

Run: `rg -n "Knowledge Map|concept learning|Home|Review|Imports" frontend/src/lib/auth-nav.tsx docs/status/project-status.md`

**Step 3: Write minimal implementation**

- Update nav labels if needed.
- Add a concise status-board entry with fresh evidence after verification succeeds.

**Step 4: Re-run the verification check**

Run: `rg -n "Knowledge Map|concept learning|Home|Review|Imports" frontend/src/lib/auth-nav.tsx docs/status/project-status.md`

**Step 5: Commit**

Commit message: `docs: record learner knowledge map status`

---

### Task 9: Run final verification

**Files:**
- No code changes expected

**Step 1: Run backend verification**

Run: `/Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_learner_knowledge_models.py backend/tests/test_knowledge_map_api.py backend/tests/test_user_preferences_api.py backend/tests/test_words.py backend/tests/test_review_models.py backend/tests/test_review_service.py -q`

**Step 2: Run frontend verification**

Run: `npm --prefix frontend test -- --runInBand frontend/src/lib/__tests__/knowledge-map-client.test.ts frontend/src/lib/__tests__/user-preferences-client.test.ts frontend/src/app/__tests__/knowledge-map-page.test.tsx frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx frontend/src/app/review/__tests__/page.test.tsx`

**Step 3: Run frontend lint/build**

Run: `npm --prefix frontend run lint`

Run: `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix frontend run build`

**Step 4: Report evidence**

- Capture pass/fail counts, notable warnings, and anything not run.
