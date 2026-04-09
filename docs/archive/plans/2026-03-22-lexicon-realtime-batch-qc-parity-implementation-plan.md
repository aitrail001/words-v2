# Lexicon Realtime and Batch QC Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make realtime lexicon generation pass through the same shared QC, labeling, and review-queue preparation path as batch generation for `word`, `phrase`, and `reference` rows, while preserving current immediate realtime validation and keeping batch transport concerns separate.

**Architecture:** Extract a shared review-prep layer at the normalized artifact-row boundary, refactor batch QC to call it, then wire realtime artifact outputs into the same service. Keep `custom_id`, retry lineage, and batch ledgers batch-only; unify only the post-normalization review-prep behavior.

**Tech Stack:** Python CLI tooling under `tools/lexicon`, existing compiled validators, FastAPI admin services, JSONL artifacts, pytest, admin/frontend tests where review metadata contracts are exposed.

---

### Task 1: Add failing unit tests for a shared review-prep boundary

**Files:**
- Create: `tools/lexicon/tests/test_review_prep.py`
- Reference: `tools/lexicon/qc.py`
- Reference: `backend/app/services/lexicon_jsonl_reviews.py`

**Step 1: Write the failing tests**

Add tests that define normalized `word`, `phrase`, and `reference` rows and expect a shared helper to produce:

- warning labels
- review priority
- review verdict semantics
- review queue rows

Add parity-style expectations so equivalent rows do not depend on whether the caller says `origin="realtime"` or `origin="batch"`.

**Step 2: Run test to verify it fails**

Run:

```bash
.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_review_prep.py -q
```

Expected: failure because no shared review-prep module exists yet.

**Step 3: Write minimal implementation**

Create a new shared helper module, likely `tools/lexicon/review_prep.py`, with functions that compute:

- warning labels
- review priority
- verdict rows
- review queue rows

Use normalized artifact rows as input.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add tools/lexicon/review_prep.py tools/lexicon/tests/test_review_prep.py
git commit -m "feat(lexicon): add shared review prep helpers"
```

### Task 2: Refactor batch QC to use the shared review-prep helpers

**Files:**
- Modify: `tools/lexicon/qc.py`
- Modify: `tools/lexicon/tests/test_qc.py`
- Modify: `tools/lexicon/tests/test_batch_lifecycle.py`

**Step 1: Write the failing/refactoring tests**

Update the QC tests so they assert batch QC now delegates shared warning/priority/verdict behavior while preserving:

- `custom_id`
- batch review notes
- manual override application
- queue output shape

**Step 2: Run targeted tests to verify current behavior breaks**

Run:

```bash
.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_qc.py tools/lexicon/tests/test_batch_lifecycle.py -q
```

Expected: failure once assertions are tightened for the shared helper behavior.

**Step 3: Write minimal implementation**

Refactor `tools/lexicon/qc.py` so it becomes a thin batch wrapper that:

- loads batch result rows
- maps them into the shared review-prep input shape
- preserves batch-only lineage fields
- writes QC and queue artifacts

**Step 4: Run targeted tests to verify they pass**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add tools/lexicon/qc.py tools/lexicon/tests/test_qc.py tools/lexicon/tests/test_batch_lifecycle.py
git commit -m "refactor(lexicon): route batch qc through shared review prep"
```

### Task 3: Add failing realtime integration tests for review-prep artifacts

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Reference: `tools/lexicon/enrich.py`
- Reference: `tools/lexicon/cli.py`

**Step 1: Write the failing tests**

Add coverage that expects realtime enrichment or its follow-on command path to produce review-prep outputs for:

- `word`
- `phrase`
- `reference`

The tests should prove:

- invalid raw realtime payloads still fail before review-prep
- valid normalized rows produce review-prep metadata and queue artifacts

**Step 2: Run targeted tests to verify it fails**

Run:

```bash
.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q
```

Expected: failure because realtime does not yet emit shared review-prep artifacts.

**Step 3: Write minimal implementation**

Wire realtime post-normalization outputs into the shared review-prep layer.

Preferred shape:

- either emit review-prep sidecar artifacts during or immediately after realtime artifact writing
- or add an explicit CLI step that runs automatically in the realtime operator path

Do not introduce synthetic batch ledgers.

**Step 4: Run targeted tests to verify they pass**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py
git commit -m "feat(lexicon): add realtime review prep parity"
```

### Task 4: Add failing validation tests for family parity at the compiled-row boundary

**Files:**
- Modify: `tools/lexicon/tests/test_compile_export.py`
- Modify: `tools/lexicon/tests/test_validate.py`
- Modify: `tools/lexicon/tests/test_review_materialize.py`

**Step 1: Write the failing tests**

Add tests that prove equivalent compiled rows across `word`, `phrase`, and `reference` families receive the same review-prep treatment regardless of origin.

Also assert `review_materialize` continues to consume approved/rejected outputs unchanged.

**Step 2: Run targeted tests to verify it fails**

Run:

```bash
.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_review_materialize.py -q
```

Expected: failure until the shared review-prep outputs are fully aligned with compiled-row expectations.

**Step 3: Write minimal implementation**

Adjust the compiled-row review-prep path and any helper contracts so family parity is explicit and stable.

**Step 4: Run targeted tests to verify they pass**

Run the same pytest command and confirm green.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_review_materialize.py
git commit -m "test(lexicon): cover family review prep parity"
```

### Task 5: Converge admin JSONL-review warning logic on the shared review-prep contract

**Files:**
- Modify: `backend/app/services/lexicon_jsonl_reviews.py`
- Modify: `backend/app/api/lexicon_jsonl_reviews.py`
- Modify: `backend/tests/test_lexicon_jsonl_reviews_api.py`
- Modify: `admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts`
- Modify: `admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx`

**Step 1: Write the failing tests**

Add coverage that expects JSONL review metadata to come from the shared review-prep contract, not an independent backend-only warning heuristic.

The test should verify:

- consistent labels and priority for compiled rows
- `word`, `phrase`, and `reference` family support

**Step 2: Run the tests to verify failure**

Run:

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jsonl_reviews_api.py -q
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx
```

Expected: failure until the backend service consumes the shared contract.

**Step 3: Write minimal implementation**

Replace the duplicated JSONL-review warning derivation with shared review-prep logic or a shared serialized artifact contract.

**Step 4: Run tests to verify they pass**

Run the same commands and confirm green.

**Step 5: Commit**

```bash
git add backend/app/services/lexicon_jsonl_reviews.py backend/app/api/lexicon_jsonl_reviews.py backend/tests/test_lexicon_jsonl_reviews_api.py admin-frontend/src/lib/lexicon-jsonl-reviews-client.ts admin-frontend/src/app/lexicon/jsonl-review/__tests__/page.test.tsx
git commit -m "refactor(admin): share review prep metadata for jsonl review"
```

### Task 6: Update operator docs and status

**Files:**
- Modify: `tools/lexicon/docs/batch.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Document the new parity model**

Update docs to state clearly:

- realtime keeps immediate schema validation
- batch keeps transport lineage
- both now share the same post-normalization review-prep workflow

**Step 2: Record live status**

Add a status log entry describing the new shared review-prep path and verification evidence.

**Step 3: Verify formatting**

Run:

```bash
git diff --check
```

Expected: pass.

**Step 4: Commit**

```bash
git add tools/lexicon/docs/batch.md tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md
git commit -m "docs(lexicon): document realtime and batch review parity"
```

### Task 7: Run the full verification set

**Files:**
- Verify only

**Step 1: Run lexicon targeted suites**

```bash
.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_review_prep.py tools/lexicon/tests/test_qc.py tools/lexicon/tests/test_batch_lifecycle.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_review_materialize.py -q
```

Expected: pass.

**Step 2: Run backend JSONL-review verification**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_lexicon_jsonl_reviews_api.py -q
```

Expected: pass.

**Step 3: Run frontend verification**

```bash
npm --prefix admin-frontend test -- --runInBand src/app/lexicon/jsonl-review/__tests__/page.test.tsx
npm --prefix admin-frontend run lint
NEXT_PUBLIC_API_URL=http://backend:8000/api npm --prefix admin-frontend run build
```

Expected: pass.

**Step 4: Run Python compile check**

```bash
PYTHONPATH=backend .venv-backend/bin/python -m py_compile backend/app/services/lexicon_jsonl_reviews.py backend/app/api/lexicon_jsonl_reviews.py tools/lexicon/review_prep.py tools/lexicon/qc.py tools/lexicon/enrich.py tools/lexicon/cli.py
```

Expected: pass.

**Step 5: Final commit if needed**

```bash
git status --short
```

If anything remains unstaged from verification-related doc/test updates, commit it with a focused message before opening a PR.
