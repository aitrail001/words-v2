# Admin Lexicon Portal Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the admin lexicon portal into first-class `Words` and `Operations` surfaces, demote staged review to a legacy page, and expand the DB inspector to show the full current word schema.

**Architecture:** Keep the existing backend routes for lexicon ops and staged review, but move the review UI to a legacy route and add a dedicated words-inspector route. Expand the existing word enrichment/detail API so the frontend can render all persisted word and meaning fields plus translations and provenance metadata without inventing a second overlapping inspector endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js App Router, React, TypeScript, Jest, pytest.

---

### Task 1: Add failing backend tests for the missing word-detail fields

**Files:**
- Modify: `backend/tests/test_words.py`
- Inspect: `backend/app/api/words.py`

**Step 1: Write backend assertions for newly required response fields**

- Cover word-level fields:
  - `word_forms`
  - `source_type`
  - `source_reference`
  - `created_at`
- Cover meaning-level fields:
  - `source`
  - `source_reference`
  - `created_at`
  - `translations`

**Step 2: Run the focused backend test**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_words.py -q`

Expected: FAIL because the API response does not yet include the new fields.

### Task 2: Expand the backend word detail contract

**Files:**
- Modify: `backend/app/api/words.py`

**Step 1: Add response models for translations and expanded meaning/word fields**

- Extend the response schema instead of creating a new endpoint.

**Step 2: Load and serialize translations**

- Query translations for the selected meanings.
- Group them by meaning.

**Step 3: Return the full persisted fields needed by the admin words inspector**

- Include the missing word-level and meaning-level provenance fields.

**Step 4: Re-run the focused backend test**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_words.py -q`

Expected: PASS

### Task 3: Add failing frontend tests for the split admin IA

**Files:**
- Add: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx` updates
- Add: `admin-frontend/src/app/lexicon/words/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/__tests__/layout-auth-nav.test.tsx`
- Inspect: `admin-frontend/src/app/lexicon/page.tsx`
- Inspect: `admin-frontend/src/app/lexicon/ops/page.tsx`

**Step 1: Update the lexicon landing-page test expectations**

- Expect links/cards for:
  - `Words`
  - `Operations`
  - `Legacy Review`

**Step 2: Add tests for the dedicated words inspector page**

- Search and selection flow
- Rendering of the newly added backend fields
- Rendering of translations and provenance fields

**Step 3: Update nav tests**

- Reflect the new page structure and links.

**Step 4: Run the focused frontend tests**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/__tests__/page.test.tsx src/app/lexicon/words/__tests__/page.test.tsx src/app/__tests__/layout-auth-nav.test.tsx`

Expected: FAIL until the routes/components are updated.

### Task 4: Split the admin routes and move the review UI to legacy

**Files:**
- Modify: `admin-frontend/src/app/lexicon/page.tsx`
- Add: `admin-frontend/src/app/lexicon/words/page.tsx`
- Add: `admin-frontend/src/app/lexicon/review/page.tsx`
- Modify: `admin-frontend/src/lib/auth-nav.tsx`

**Step 1: Turn `/lexicon` into a landing page**

- Replace the mixed tabbed UI with a simple section index.

**Step 2: Move the current staged-review UI to `/lexicon/review`**

- Preserve behavior.
- Add legacy framing copy.

**Step 3: Move the DB inspector to `/lexicon/words`**

- Extract only the word-search and detail-inspection workflow.

**Step 4: Update admin navigation**

- Make `Words` and `Operations` primary.
- Keep `Legacy Review` present but clearly secondary.

### Task 5: Expand the frontend words client and words inspector rendering

**Files:**
- Modify: `admin-frontend/src/lib/words-client.ts`
- Modify: `admin-frontend/src/app/lexicon/words/page.tsx`

**Step 1: Extend frontend types to match the backend contract**

- Add word-level fields:
  - `word_forms`
  - `source_type`
  - `source_reference`
  - `created_at`
- Add meaning-level fields:
  - `source`
  - `source_reference`
  - `created_at`
  - `translations`

**Step 2: Render all persisted fields in readable sections**

- summary cards
- word record
- meanings
- examples
- relations
- translations
- enrichment provenance

**Step 3: Ensure empty-state and null rendering are explicit**

- Use `—` or equivalent absent-value rendering consistently.

### Task 6: Refresh wording on Lexicon Operations

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify: `admin-frontend/src/app/page.tsx`

**Step 1: Clarify that ops is for offline snapshot/artifact monitoring**

- Make the title/description match the active workflow.

**Step 2: Add cross-links where useful**

- Link from the landing page to operations.
- Optionally link from legacy review to ops and words.

### Task 7: Run verification for backend and admin frontend

**Files:**
- Verify: `backend/tests/test_words.py`
- Verify: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Verify: `admin-frontend/src/app/lexicon/words/__tests__/page.test.tsx`
- Verify: `admin-frontend/src/app/__tests__/layout-auth-nav.test.tsx`
- Verify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`

**Step 1: Run backend verification**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_words.py -q`

**Step 2: Run targeted admin frontend verification**

Run: `npm --prefix admin-frontend test -- --runInBand src/app/lexicon/__tests__/page.test.tsx src/app/lexicon/words/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx src/app/__tests__/layout-auth-nav.test.tsx`

**Step 3: Run broader admin frontend checks**

Run:
- `npm --prefix admin-frontend test -- --runInBand`
- `npm --prefix admin-frontend run lint`
- `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build`

### Task 8: Update status board if the admin IA ships

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update the relevant admin/lexicon status row**

- Record that the admin IA now reflects the current operator path.
- Include exact verification evidence.

**Step 2: Append a dated status change log entry**

- Keep the entry concise and evidence-based.
