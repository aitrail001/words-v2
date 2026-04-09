# Admin Lexicon Nav And Import Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the admin lexicon top navigation, add Voice/DB/Enrichment Review section submenus, split voice storage and voice runs into separate routes, compact the two lexicon import forms, and refresh the live policy display after voice policy apply.

**Architecture:** Keep backend contracts intact while reshaping the admin frontend route shell. Add a reusable section-nav component, split the current voice page into dedicated storage and runs pages, retarget the top-level Voice and Lexicon Ops entry points, tighten the two import-page form grids, and wire the voice storage page so a successful policy apply re-fetches the current DB storage-policy list from the backend.

**Tech Stack:** Next.js App Router, React, TypeScript, Jest Testing Library

---

### Task 1: Add failing navigation tests for the new menu structure

**Files:**
- Modify: `admin-frontend/src/lib/auth-nav.tsx`
- Modify: `admin-frontend/src/app/__tests__/page.test.tsx`

- [ ] **Step 1: Extend the nav expectations in tests**

Add assertions for:
- `Home`
- `Lexicon Ops`
- `Voice`
- `Enrichment Review`
- `DB`
- `Logout` or `Log In` depending on auth state

- [ ] **Step 2: Run the targeted nav test to verify it fails**

Run: `pnpm --dir admin-frontend test -- --runInBand src/app/__tests__/page.test.tsx`

Expected: FAIL because current nav still renders `Lexicon Voice`, `Compiled Review`, `JSONL Review`, `Import DB`, and `DB Inspector`.

- [ ] **Step 3: Update the shared nav labels and destinations**

Change `auth-nav.tsx` so:
- `Voice` links to `/lexicon/voice`
- `Enrichment Review` links to `/lexicon/compiled-review`
- `DB` links to `/lexicon/import-db`
- remove the separate top-level `JSONL Review`, `Import DB`, and `DB Inspector` entries

- [ ] **Step 4: Re-run the targeted nav test**

Run: `pnpm --dir admin-frontend test -- --runInBand src/app/__tests__/page.test.tsx`

Expected: PASS

### Task 2: Add failing tests for lexicon section submenus and policy refresh

**Files:**
- Create: `admin-frontend/src/components/lexicon/section-nav.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

- [ ] **Step 1: Add test coverage for Voice and DB submenus**

Add assertions that:
- the voice page renders submenu items for `Storage`, `Voice Runs`, and `Voice DB Import`
- the import-db page renders submenu items for `Enrichment Import` and `DB Inspector`

- [ ] **Step 2: Add a voice-page test for post-apply policy refresh**

Mock `getLexiconVoiceStoragePolicies` to return one response on initial load and a changed response after apply. Assert the page re-queries policies after a successful non-dry-run apply and shows the refreshed policy base.

- [ ] **Step 3: Run the targeted page tests to verify they fail**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice lexicon/import-db`

Expected: FAIL because no section submenu exists and the voice page does not yet refresh the policy list after apply.

- [ ] **Step 4: Add the reusable section-nav component and wire the pages**

Implement a compact lexicon section-nav component and render it from the voice, voice-import, import-db, and db-inspector pages with the correct active item.

- [ ] **Step 5: Wire post-apply policy refresh**

Add a callback from the voice page into the voice storage panel so a successful apply triggers a fresh `getLexiconVoiceStoragePolicies(undefined)` fetch.

- [ ] **Step 6: Re-run the targeted page tests**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice lexicon/import-db`

Expected: PASS

### Task 3: Add failing tests for compact import form layouts

**Files:**
- Modify: `admin-frontend/src/app/lexicon/voice-import/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice-import/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`

- [ ] **Step 1: Add layout-oriented expectations**

Assert that the pages render:
- the section submenu
- compact form groups with all required inputs still present
- unchanged dry-run and import buttons

- [ ] **Step 2: Run the targeted import-page tests to verify they fail**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice-import lexicon/import-db`

Expected: FAIL because the current pages use the older single-grid arrangement and do not yet render the new section submenu.

- [ ] **Step 3: Refactor both pages to use compact two-row form grids**

Keep the same state and request payloads, but recompose the JSX into tighter grouped rows.

- [ ] **Step 4: Re-run the targeted import-page tests**

Run: `pnpm --dir admin-frontend test -- --runInBand lexicon/voice-import lexicon/import-db`

Expected: PASS

### Task 4: Record the UI state change and run final verification

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a status-log entry**

Record the navigation/layout refresh and the policy-refresh behavior with verification evidence.

- [ ] **Step 2: Run the full targeted verification set**

Run: `pnpm --dir admin-frontend exec eslint src/lib/auth-nav.tsx src/components/lexicon/section-nav.tsx src/app/lexicon/voice/page.tsx src/app/lexicon/voice/voice-storage-panel.tsx src/app/lexicon/voice-import/page.tsx src/app/lexicon/import-db/page.tsx src/app/lexicon/db-inspector/page.tsx src/app/lexicon/voice/__tests__/page.test.tsx src/app/lexicon/voice-import/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx src/app/__tests__/page.test.tsx --max-warnings=0`

Expected: PASS

- [ ] **Step 3: Run the final frontend tests**

Run: `pnpm --dir admin-frontend test -- --runInBand src/app/__tests__/page.test.tsx lexicon/voice lexicon/voice-import lexicon/import-db lexicon/db-inspector`

Expected: PASS

### Task 5: Extend DB import recent-jobs browsing

**Files:**
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

- [ ] **Step 1: Add a failing DB-import recent-jobs expansion test**

Assert that:
- DB import still shows only the inline recent-job slice by default
- a `Show all recent jobs` control appears when more than six jobs exist
- clicking it reveals the additional jobs and changes the control to `Show fewer recent jobs`

- [ ] **Step 2: Run the targeted DB import test**

Run: `pnpm --dir admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx`

Expected: FAIL because the current page only fetches and renders six jobs with no expansion control.

- [ ] **Step 3: Add DB import recent-jobs expansion parity**

Mirror the voice-import pattern:
- fetch a larger recent-job window
- render the first six inline by default
- add a show-all/show-fewer toggle
- collapse automatically when the fetched job count drops back to six or fewer

- [ ] **Step 4: Re-run the targeted DB import test**

Run: `pnpm --dir admin-frontend test -- --runInBand src/app/lexicon/import-db/__tests__/page.test.tsx`

Expected: PASS
