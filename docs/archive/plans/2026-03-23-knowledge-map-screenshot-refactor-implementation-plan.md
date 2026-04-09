# Knowledge Map Screenshot Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the learner knowledge-map frontend so the home and detail flows match the provided mobile screenshots much more closely while keeping the existing learner APIs and behaviors intact.

**Architecture:** Keep the current backend contracts and client fetching logic, but replace the current desktop split-page composition with a mobile-first, screenshot-aligned layout. Build around reusable presentational helpers inside the existing page files, preserve the three range views and learner status actions, and add test coverage for the new layout markers and behaviors before implementation.

**Tech Stack:** Next.js App Router, React client components, Tailwind CSS, Jest + Testing Library

---

### Task 1: Redesign the home-page test expectations

**Files:**
- Modify: `frontend/src/app/__tests__/page.test.tsx`

**Step 1: Write the failing test**

- Assert the screenshot-aligned structure instead of the desktop split layout:
  - `Full knowledge map`
  - the numbered 100-range tile grid
  - card CTA buttons `Should Learn` and `Already Know`
  - a bottom range strip / mini-map marker
  - tags and list view markers aligned to the reference UX

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/page.test.tsx`

Expected: FAIL because the current page still uses the old desktop composition and does not expose the new layout markers.

**Step 3: Write minimal implementation**

- Update `frontend/src/app/page.tsx` only after the failing test is confirmed.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/page.test.tsx`

Expected: PASS

### Task 2: Redesign the detail-page test expectations

**Files:**
- Modify: `frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

**Step 1: Write the failing test**

- Assert the screenshot-aligned detail structure:
  - full-width hero image region
  - overlay-style top controls
  - stacked definition card
  - `Pro Tips` section
  - bottom learner status bar / primary CTA area

**Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

Expected: FAIL because the current detail page is still a two-column desktop layout.

**Step 3: Write minimal implementation**

- Update `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx` only after the failing test is confirmed.

**Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

Expected: PASS

### Task 3: Refactor the learner home page to the screenshot-aligned mobile layout

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/globals.css`

**Step 1: Replace the top-level page composition**

- Move from the current desktop split layout to:
  - top app-bar style heading
  - explanatory copy
  - dense numbered tile grid
  - active card / tags / list viewport
  - bottom mini-map range navigator

**Step 2: Preserve existing behaviors**

- Keep:
  - range loading
  - search + recent search history
  - status mutation
  - `cards`, `tags`, `list`
  - `Learn More`

**Step 3: Re-style the page to match the reference**

- Introduce:
  - purple/cyan accent system
  - lighter mobile canvas
  - image-first card
  - stronger rounded panels and compact spacing

**Step 4: Re-run home tests**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/__tests__/page.test.tsx`

Expected: PASS

### Task 4: Refactor the learner detail page to the screenshot-aligned stacked mobile layout

**Files:**
- Modify: `frontend/src/app/knowledge/[entryType]/[entryId]/page.tsx`

**Step 1: Replace the two-column page structure**

- Move to:
  - hero image on top
  - floating/overlay top controls
  - stacked definition card
  - `Pro Tips` blocks derived from existing meaning/sense/example data
  - bottom persistent learner actions

**Step 2: Preserve existing behaviors**

- Keep:
  - status updates
  - previous/next navigation
  - search from detail
  - recent searches

**Step 3: Add graceful content fallbacks**

- If real image/pro-tip content is absent:
  - keep the current placeholder strategy
  - project examples/definitions into the tip cards

**Step 4: Re-run detail tests**

Run: `npm --prefix frontend test -- --runInBand frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx`

Expected: PASS

### Task 5: Run targeted verification for the frontend slice

**Files:**
- Verify only

**Step 1: Run the targeted Jest coverage**

Run:

```bash
npm --prefix frontend test -- --runInBand \
  frontend/src/app/__tests__/page.test.tsx \
  frontend/src/app/knowledge/[entryType]/[entryId]/__tests__/page.test.tsx
```

Expected: PASS

**Step 2: Run lint**

Run: `npm --prefix frontend run lint`

Expected: PASS

**Step 3: Run production build**

Run: `NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix frontend run build`

Expected: PASS

### Task 6: Update live status if the verification evidence changes materially

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Add fresh evidence**

- Record the screenshot-alignment frontend follow-up and the fresh verification commands.

**Step 2: Final verification**

Run: `git diff --check`

Expected: PASS
