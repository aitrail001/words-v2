# Lexicon Admin Portal Enhancement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix compiled-review materialization and unify the affected lexicon admin portal pages under a shared workspace pattern with staged Ops artifacts and richer DB Inspector detail.

**Architecture:** Keep the current routes and feature ownership, add lexicon-only shared admin workspace components in the admin frontend, and make targeted additive backend changes for compiled-review materialization safety plus richer inspector and ops presentation data.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js app router, React client components, Jest + Testing Library, pytest.

---

### Task 1: Write the failing backend regression for compiled-review materialize

**Files:**
- Modify: `backend/tests/test_lexicon_compiled_reviews_api.py`
- Test: `backend/tests/test_lexicon_jsonl_reviews_api.py`

**Step 1: Add the failing regression**

Add a compiled-review materialize test that stores a DB-backed review item payload containing values that currently trigger the `500` path during JSON serialization/materialization.

Also add or tighten a JSONL review materialize assertion proving the JSONL path still materializes successfully under the same logical payload shape.

**Step 2: Run the focused backend tests to verify failure**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

Expected: FAIL in the compiled-review regression before implementation.

### Task 2: Fix compiled-review materialize serialization safely

**Files:**
- Modify: `backend/app/api/lexicon_compiled_reviews.py`
- Reference: `backend/app/services/lexicon_jsonl_reviews.py`

**Step 1: Normalize materialized rows before write**

Implement a minimal JSON-safe normalization path for compiled-review exported/materialized rows so ORM-backed values are converted into JSONL-safe primitives before `json.dumps(...)`.

**Step 2: Keep output contracts stable**

Preserve:

- `review.decisions.jsonl`
- `approved.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`

Do not widen the file contract beyond safe normalization and clearer failure handling.

**Step 3: Re-run focused backend tests**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

Expected: PASS.

### Task 3: Add failing backend tests for richer DB Inspector and staged Ops artifacts

**Files:**
- Modify: `backend/tests/test_lexicon_inspector_api.py`
- Modify: `backend/tests/test_lexicon_ops_api.py`

**Step 1: Add inspector detail expectations**

Add tests expecting richer word-detail payload fields and structured meaning/example/relation presentation inputs needed by the new UI.

**Step 2: Add ops grouping expectations if backend grouping is needed**

If the UI needs server-provided stage/purpose metadata, add focused failing tests for the grouped artifact response shape.

**Step 3: Run focused backend tests**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py backend/tests/test_lexicon_ops_api.py -q
```

Expected: FAIL only for the new expectations.

### Task 4: Implement richer backend detail/grouping support

**Files:**
- Modify: `backend/app/api/lexicon_inspector.py`
- Modify if needed: `backend/app/api/lexicon_ops.py`

**Step 1: Expand DB Inspector detail payloads**

Add the top-level fields and subpanel-oriented detail data required by the redesigned inspector.

**Step 2: Add staged artifact grouping data if needed**

If frontend-only grouping is insufficient, expose a stable grouped artifact shape from the ops endpoint.

**Step 3: Re-run focused backend tests**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py backend/tests/test_lexicon_ops_api.py -q
```

Expected: PASS.

### Task 5: Write failing frontend tests for the shared lexicon workspace

**Files:**
- Add: `admin-frontend/src/components/lexicon/*` as needed
- Modify: `admin-frontend/src/app/lexicon/compiled-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Modify if needed: `admin-frontend/src/lib/lexicon-inspector-client.ts`
- Modify if needed: `admin-frontend/src/lib/lexicon-ops-client.ts`

**Step 1: Add Compiled Review expectations**

Add tests for:

- horizontal batch rail behavior
- entry list pagination to `10` items per page
- wider detail workspace with raw JSON panel and decision panel

**Step 2: Add JSONL Review expectations**

Add tests for:

- shared workspace layout parity
- paged entry list behavior
- raw JSON/detail panel structure

**Step 3: Add DB Inspector and Ops expectations**

Add tests for:

- richer detail rendering in DB Inspector
- staged tracked-artifact grouping in Ops

**Step 4: Run focused frontend tests to verify failure**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: FAIL on the new workspace/grouping/detail expectations.

### Task 6: Implement shared lexicon workspace components and page migrations

**Files:**
- Add/Modify: `admin-frontend/src/components/lexicon/*`
- Modify: `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/ops/page.tsx`
- Modify if needed: `admin-frontend/src/lib/lexicon-inspector-client.ts`
- Modify if needed: `admin-frontend/src/lib/lexicon-ops-client.ts`

**Step 1: Build lexicon-only shared workspace primitives**

Extract the smallest useful shared components for:

- top rails
- paged left lists
- detail panels
- raw JSON panels
- common metadata blocks

**Step 2: Migrate Compiled Review**

Implement:

- horizontal batch rail
- paged entry rail
- wide detail workspace

**Step 3: Migrate JSONL Review**

Apply the same workspace pattern while preserving JSONL-specific semantics.

**Step 4: Upgrade DB Inspector and Ops presentation**

Render the richer detail and staged artifact grouping using the shared panel language.

**Step 5: Re-run focused frontend tests**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: PASS.

### Task 7: Update live status and run final verification

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record the portal enhancement**

Add a status log entry describing:

- compiled-review materialize hardening
- shared lexicon workspace alignment
- staged Ops artifact grouping
- richer DB Inspector detail

Include fresh verification evidence.

**Step 2: Run the final targeted verification set**

Run:

```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_lexicon_compiled_reviews_api.py backend/tests/test_lexicon_jsonl_reviews_api.py backend/tests/test_lexicon_inspector_api.py backend/tests/test_lexicon_ops_api.py -q
NODE_PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/admin-frontend/node_modules/.bin:$PATH npm --prefix admin-frontend test -- --runInBand src/app/lexicon/compiled-review/__tests__/page.test.tsx src/app/lexicon/jsonl-review/__tests__/page.test.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/app/lexicon/ops/__tests__/page.test.tsx
```

Expected: PASS.

**Step 3: Stop before commit if any verification fails**

Do not claim completion without fresh passing output.
