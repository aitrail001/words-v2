# Learner Follow-Up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the deferred learner follow-up work after the phrase-contract/performance slice: show two examples in learner detail, audit and reduce remaining JSON-heavy lexicon storage outside learner hot paths, and add durable learner request/query instrumentation.

**Architecture:** Keep the finished normalized phrase learner contract intact. Add instrumentation first, then implement the two-example detail UI using the existing ordered detail payloads, then perform a bounded JSON-column audit and normalize only the next justified cluster.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Postgres, Next.js/React, TypeScript, pytest/Jest/Playwright, structured logging

---

### Task 1: Add learner endpoint instrumentation

**Files:**
- Modify: `backend/app/api/knowledge_map.py`
- Modify if needed: backend request/session instrumentation helpers
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `docs/status/project-status.md`

**Step 1: Write failing backend tests**

Add focused tests that prove learner endpoint responses emit or attach request-local timing/query summary information through the chosen instrumentation seam.

Keep the seam pragmatic:

- structured log assertion
- response header assertion in debug/test mode
- or request-context collector assertion

Do not design a heavyweight metrics backend first.

**Step 2: Implement narrow backend instrumentation**

Capture:

- route name
- request duration
- DB query count
- DB query duration total

Keep it low-cardinality and learner-route-scoped.

**Step 3: Verify**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: PASS.

### Task 2: Show two examples on learner detail surfaces

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
- Modify if needed: `frontend/src/lib/knowledge-map-client.ts`
- Modify if needed: backend detail tests only if a truncation guard is required

**Step 1: Write failing frontend tests**

Add rendered-behavior tests proving:

- word meanings show two ordered examples when available
- phrase senses show two ordered examples when available
- translations remain aligned to the matching example
- one-example meanings/senses still render correctly

**Step 2: Implement narrow UI change**

Render up to two examples per meaning/sense on detail pages only. Do not expand list/range cards in this task.

**Step 3: Verify**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

### Task 3: Run targeted live verification for instrumentation and second-example rendering

**Files:**
- No code changes expected unless a bug surfaces

**Step 1: Backend verification**

Run the learner backend verification bundle.

**Step 2: Frontend verification**

Run the focused learner detail test suite and lint if needed.

**Step 3: Live Docker verification**

Run the targeted learner smoke and capture learner endpoint timing evidence using the new instrumentation.

Expected: PASS with observable timing/query summaries.

### Task 4: Audit remaining significant JSON-heavy lexicon columns

**Files:**
- Create: `docs/plans/2026-03-26-lexicon-json-audit.md`
- Inspect relevant backend models/importer code as needed

**Step 1: Produce a bounded audit**

For each significant remaining JSON-heavy lexicon column, record:

- file/model/table/column
- current owner/path
- whether it is learner-serving, admin-serving, provenance, or transitional
- current risks
- recommended disposition: keep, normalize later, or normalize now

**Step 2: Choose one justified normalization target**

Pick only one next cluster for implementation. Prefer the cluster with the strongest combination of:

- semantic structure
- repeated access
- validation needs
- maintenance pain

### Task 5: Normalize the chosen non-hot-path JSON cluster

**Files:**
- Determined by Task 4 audit

**Step 1: Write failing tests first**

Add model/import/API tests only for the chosen cluster.

**Step 2: Implement narrowly**

Move the chosen cluster into structured persistence while keeping any useful raw provenance payload.

**Step 3: Verify**

Run the smallest meaningful backend/import verification set for that cluster.

### Task 6: Update project status with evidence

**Files:**
- Modify: `docs/status/project-status.md`

Record:

- instrumentation landing
- two-example learner detail behavior
- JSON audit result
- any normalized follow-up cluster and exact verification evidence
