# Inline Pickup Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a compact inline pickup overlay for linked learner terms and remove duplicated relation rendering from the standalone detail page.

**Architecture:** Keep the work inside the learner detail component by reusing the existing learner detail API. Inline linked terms open a small overlay that fetches the linked entry detail on demand, while full navigation remains available only through a dedicated `Look up` action.

**Tech Stack:** Next.js, React, Jest, existing learner detail API/client.

---

### Task 1: Add failing UI tests for the pickup overlay

**Files:**
- Modify: `frontend/src/app/word/[entryId]/__tests__/page.test.tsx`

**Steps:**
1. Add a test that clicks an example-linked term and expects a pickup overlay with `Look up` and `Got it!`.
2. Add assertions that the overlay closes on `Got it!`.
3. Add an assertion that duplicate relation-group content does not render when sense links are already present.

### Task 2: Implement inline sentence linking and shared overlay state

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`

**Steps:**
1. Add overlay state for the selected linked entry and its loaded detail payload.
2. Replace direct inline `Link` usage for learner-linked chips/terms with overlay-opening buttons.
3. Render example terms inline within the sentence where possible instead of as a separate chip row.
4. Add the compact pickup overlay with `Look up` and `Got it!`.

### Task 3: Remove duplicated relation rendering

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`

**Steps:**
1. Keep `Sense Links` as the canonical relation section.
2. Remove repeated `relation_groups` cards from the lower `Pro Tips` area.
3. Keep confusable words and other non-duplicate guidance sections.

### Task 4: Verify the learner flow

**Files:**
- Modify if needed: `e2e/tests/smoke/knowledge-map.smoke.spec.ts`

**Steps:**
1. Run the focused Jest test file for the word detail route.
2. Run frontend lint.
3. Run the targeted learner smoke against the live Docker stack.
