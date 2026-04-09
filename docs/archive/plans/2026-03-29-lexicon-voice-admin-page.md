# Lexicon Voice Admin Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move voice generation/storage admin controls out of the crowded Lexicon Ops page into a dedicated `/lexicon/voice` page while keeping the current backend rewrite contract unchanged.

**Architecture:** Add a focused admin page for voice storage operations, linked from the auth nav and from the Lexicon Ops workflow surface. Keep the current rewrite API and client intact, but render the storage-rewrite form and result summary on the new page instead of inside `/lexicon/ops`.

**Tech Stack:** Next.js app router, React client components, Jest/RTL, existing lexicon ops API client

---

### Task 1: Add failing frontend tests

**Files:**
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/__tests__/layout-auth-nav.test.tsx`
- Create: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`

### Task 2: Implement dedicated voice page

**Files:**
- Create: `admin-frontend/src/app/lexicon/voice/page.tsx`
- Create: `admin-frontend/src/app/lexicon/voice/voice-storage-panel.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify: `admin-frontend/src/lib/auth-nav.tsx`

### Task 3: Verify and record evidence

**Files:**
- Modify: `docs/status/project-status.md`
