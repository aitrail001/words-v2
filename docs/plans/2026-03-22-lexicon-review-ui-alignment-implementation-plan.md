# Lexicon Review UI Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align JSONL Review with Compiled Review interaction patterns, auto-advance to the next pending item after review actions, and add explicit confirmation controls for approve/reject/reopen.

**Architecture:** Keep the current review APIs unchanged and implement the behavior in the admin frontend review pages. Extract small queue-navigation helpers in the page components so both review modes can use the same decision progression model without changing backend contracts.

**Tech Stack:** Next.js app router, React client components, Jest + Testing Library, Playwright smoke tests.

---

### Task 1: Add failing review interaction tests

**Files:**
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`

**Step 1: Write failing tests for queue progression**

Add tests that verify:
- after approve/reject/reopen, selection moves to the next pending row when one exists
- the current row stays selected when no later pending row exists
- confirmation controls are present before the final action fires

**Step 2: Run the focused tests to verify failure**

Run:
```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/compiled-review/__tests__/page.test.tsx
```

Expected: FAIL on missing confirmation controls and missing auto-advance behavior.

### Task 2: Implement shared decision-flow behavior in review pages

**Files:**
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`

**Step 1: Add queue navigation helpers**

Implement minimal helpers that:
- derive the current filtered review queue
- find the next pending item after the current selection
- fall back sensibly when no later pending row exists

**Step 2: Add explicit confirmation controls**

Add compact confirm buttons or staged action affordances for:
- approve
- reject
- reopen

Requirement:
- keyboard shortcuts should still work, but should respect the confirmation pattern rather than silently firing a destructive action with no UI acknowledgement.

**Step 3: Align JSONL Review layout**

Bring JSONL Review closer to Compiled Review by:
- using the same review-action grouping
- presenting the decision area with clearer review-state structure
- preserving the current JSONL-specific summary and raw payload sections

### Task 3: Verify browser-facing behavior

**Files:**
- Modify if needed: `e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts`
- Modify if needed: `e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts`

**Step 1: Update smoke assertions**

Ensure both smokes cover:
- the confirmation action path
- auto-advance to the next pending row after a decision

**Step 2: Run targeted verification**

Run:
```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/compiled-review/__tests__/page.test.tsx
npm --prefix admin-frontend run lint
NEXT_PUBLIC_API_URL=/api BACKEND_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

Then run the review smokes in Docker.

### Task 4: Update status docs and finalize branch

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record the UI alignment and verification evidence**

Add a status row for:
- aligned review UI behavior
- queue auto-advance
- confirmation controls
- test evidence

**Step 2: Commit cleanly**

Commit only the review UI alignment slice after verification passes.
