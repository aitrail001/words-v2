# Lexicon JSONL Triage Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the JSONL-only lexicon review page into a triage-first review console that surfaces machine-derived warnings and reviewer summaries while keeping JSONL artifacts and decision sidecars as the only source of truth.

**Architecture:** Extend the file-backed backend session payload with review-oriented metadata per row, then reshape the admin frontend to sort and present rows by triage risk instead of forcing reviewers to interpret raw JSON first. Keep `review.decisions.jsonl` and `review-materialize` unchanged as the persistence/materialization boundary.

**Tech Stack:** FastAPI, Python service helpers, Next.js app router, React client components, Jest, existing admin frontend tooling.

---

### Task 1: Add failing backend tests for triage metadata

**Files:**
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py`
- Modify: `backend/app/services/lexicon_jsonl_reviews.py`

**Step 1: Write failing test**

Add coverage that loads a compiled artifact and expects each item payload to include:

1. warning labels for suspicious rows
2. a warning count / severity bucket
3. reviewer-summary fields such as sense count, forms count, and provenance summary

**Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

Expected: failure because the current response does not expose triage metadata.

**Step 3: Write minimal implementation**

Add service helpers that derive warning labels and summary fields from the compiled row and include them in the loaded session items.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

### Task 2: Add failing frontend test for triage-first ordering and summary rendering

**Files:**
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`

**Step 1: Write failing test**

Add UI coverage that expects:

1. warning-bearing rows to appear before clean rows
2. reviewer summary content to render without needing raw JSON
3. warning chips to appear in the queue and selected-item panel

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx
```

Expected: failure because the current UI neither renders the new summary fields nor sorts by warnings.

**Step 3: Write minimal implementation**

Update the page to:

1. sort queue items by warnings + pending status
2. render warning chips
3. show a summary block above the raw JSON pane

**Step 4: Run test to verify it passes**

Run the same Jest command and confirm green.

### Task 3: Verify admin frontend build/lint for the reshaped review UI

**Files:**
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`

**Step 1: Run lint**

```bash
npm --prefix admin-frontend run lint
```

Expected: pass.

**Step 2: Run production build**

```bash
NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

Expected: pass.

### Task 4: Update live project status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record the triage-review enhancement**

Add one status log line describing:

1. triage metadata exposure
2. reviewer summary rendering
3. risk-first queue ordering
4. verification evidence

**Step 2: Verify formatting**

Run:

```bash
git diff --check
```

Expected: pass.
