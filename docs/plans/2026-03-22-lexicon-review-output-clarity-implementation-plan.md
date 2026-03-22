# Lexicon Review Output Clarity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Compiled Review, JSONL-Only Review, and Import DB explain the same reviewed-artifact flow clearly, with `approved.jsonl` as the default final-import input.

**Architecture:** Keep the current review/export behavior, but clarify the artifact contract in the UI, tests, and operator docs. Do not add new review statuses. Instead, make the pages explain how `approved`, `rejected`, `decisions`, and `regenerate` are derived from `Approve`, `Reject`, and `Reopen`.

**Tech Stack:** Next.js admin frontend, FastAPI backend, Jest, Playwright, markdown docs

---

### Task 1: Lock the expected UX in tests

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx`

**Step 1: Write the failing test assertions**

Add assertions that:
- Compiled Review explains:
  - approved rows are the final import input
  - decisions are the review ledger
  - regenerate is derived from rejected rows
- JSONL Review explains the same artifact mapping
- Import DB explicitly references `approved.jsonl` as the preferred input

**Step 2: Run the targeted frontend tests to verify failure**

Run:

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

Expected: failing assertions for the new copy and labels.

### Task 2: Update the review pages and import page

**Files:**
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/import-db/page.tsx`

**Step 1: Implement the minimal UI changes**

Update the pages to:
- describe the shared artifact mapping explicitly
- rename export/materialize labels to be more descriptive
- make Compiled Review download names include snapshot/source context when possible
- make Import DB placeholder and help text prefer `approved.jsonl`

**Step 2: Re-run the targeted frontend tests**

Run the same Jest command and confirm it passes.

### Task 3: Update operator docs and status

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Document the clarified contract**

State clearly:
- `words.enriched.jsonl` is the pre-review compiled artifact
- `approved.jsonl` is the reviewed import input
- `review.decisions.jsonl` is the decision ledger
- `regenerate.jsonl` comes from rejected rows that should be regenerated

**Step 2: Verify docs references are coherent**

Run:

```bash
rg -n "approved.jsonl|words.enriched.jsonl|review.decisions.jsonl|regenerate.jsonl" tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md admin-frontend/src/app/lexicon -S
```

### Task 4: Run verification

**Files:**
- Verify touched frontend files and docs

**Step 1: Run targeted Jest**

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/import-db/__tests__/page.test.tsx
```

**Step 2: Run frontend lint**

```bash
npm --prefix admin-frontend run lint
```

**Step 3: Run frontend build**

```bash
NEXT_PUBLIC_API_URL=/api BACKEND_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

**Step 4: Run targeted Playwright smoke**

```bash
docker compose -f docker-compose.yml exec -T playwright sh -lc "cd /workspace/e2e && ./node_modules/.bin/playwright test tests/smoke/admin-compiled-review-flow.smoke.spec.ts tests/smoke/admin-jsonl-review-flow.smoke.spec.ts --project=chromium"
```

**Step 5: Commit**

```bash
git add admin-frontend/src/app/lexicon/compiled-review/page.tsx admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/jsonl-review/page.tsx admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx admin-frontend/src/app/lexicon/import-db/page.tsx admin-frontend/src/app/lexicon/import-db/__tests__/page.test.tsx tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md docs/plans/2026-03-22-lexicon-review-output-clarity-implementation-plan.md
git commit -m "fix(admin): clarify lexicon review outputs"
```
