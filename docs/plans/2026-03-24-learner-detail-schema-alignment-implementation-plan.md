# Learner Detail Schema Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix Docker migration bootstrap on fresh local stacks and align learner detail/settings behavior with the real word+phrase schema, including translated examples/usage notes, inflection fields, and exact-match related-entry links.

**Architecture:** Extend the existing knowledge-map backend service and learner detail contract instead of introducing a second detail API. Keep locale and link normalization server-side, then render the richer schema faithfully in the existing learner pages.

**Tech Stack:** Docker Compose, FastAPI, SQLAlchemy, Alembic, Next.js, React, Jest, Playwright.

---

### Task 1: Add fresh-stack migration bootstrap

**Files:**
- Modify: `docker-compose.yml`
- Test: fresh local compose startup verification

**Step 1: Write the failing verification expectation**

Document and verify that a fresh volume currently starts without the `users` table and breaks `admin@admin.com` login.

**Step 2: Update compose**

- Add a one-shot `migrate` service that runs `alembic upgrade head`
- Make `backend` and `worker` depend on successful migration completion

**Step 3: Verify on a fresh stack**

Run a fresh `docker compose down -v`, then `up`, then confirm:
- Alembic head is applied
- `users` table exists
- `admin@admin.com` login succeeds after first request bootstrap

### Task 2: Add backend tests for rich learner detail payload

**Files:**
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/knowledge_map.py`

**Step 1: Write failing backend tests**

Add targeted tests for:
- supported locale selection
- translated definition/usage note/example mapping
- forms payload rendering
- exact-match related-link resolution
- word-vs-phrase sense fidelity

**Step 2: Run the focused backend tests to verify red**

Run the targeted pytest selection and confirm failure for the missing fields.

**Step 3: Implement minimal backend contract changes**

Extend learner detail response builders and service helpers to:
- expose fixed supported locales
- expose per-sense translation payloads
- expose forms
- expose lexical sections faithfully
- resolve exact-match entry links

**Step 4: Re-run focused backend tests**

Confirm they pass.

### Task 3: Update frontend types and clients

**Files:**
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/lib/user-preferences-client.ts`
- Test: `frontend/src/lib/__tests__/*` as needed

**Step 1: Write failing frontend type/client tests where practical**

Cover new locale label expectations and richer detail payload handling.

**Step 2: Update the client contracts**

Add the new forms, localized fields, related link metadata, and locale label support.

**Step 3: Run focused frontend tests**

Confirm red-to-green on the client layer.

### Task 4: Update learner settings page

**Files:**
- Modify: `frontend/src/app/settings/page.tsx`
- Modify: `frontend/src/app/settings/__tests__/page.test.tsx`

**Step 1: Write failing settings tests**

Cover:
- full language labels
- persisted locale code mapping

**Step 2: Implement minimal settings UI changes**

Replace partial/raw locale handling with the fixed five-language list and full labels.

**Step 3: Re-run settings tests**

Confirm they pass.

### Task 5: Update learner detail rendering

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/app/word/[entryId]/__tests__/page.test.tsx`
- Modify: `frontend/src/app/phrase/[entryId]/__tests__/page.test.tsx`

**Step 1: Write failing detail tests**

Cover:
- translation toggle affects definition/examples/usage note
- pronunciation follows accent-aware payload
- forms render when present
- synonyms/collocations/confusables render per sense
- exact-match related links render as links

**Step 2: Implement minimal detail changes**

Render the richer backend payload with schema fidelity and exact-match links.

**Step 3: Re-run focused detail tests**

Confirm they pass.

### Task 6: Run integration verification on Docker with real data

**Files:**
- Reuse existing Docker and E2E helpers
- Update tests only if real-data issues surface

**Step 1: Recreate the local stack fresh**

Start from `down -v`, then `up`.

**Step 2: Import the tracked lexicon fixture**

Use the repo fixture import path to repopulate the DB.

**Step 3: Run targeted live verification**

Verify:
- admin login works without manual migration
- settings language options are correct
- detail page translation matches locale setting
- translated examples/usage notes appear when translations are on
- related exact-match links navigate correctly

### Task 7: Final verification and docs/status update

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run final checks**

- focused backend pytest
- frontend Jest for changed surfaces
- frontend lint
- frontend build
- Docker smoke / targeted Playwright
- `git diff --check`

**Step 2: Update live status**

Record the new learner detail and Docker bootstrap evidence in `docs/status/project-status.md`.

**Step 3: Prepare branch for PR**

Keep the commit focused on:
- compose bootstrap
- schema-aligned learner detail/settings
- tests and status evidence
