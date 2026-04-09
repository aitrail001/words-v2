# Learner Catalog Projection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace request-time learner catalog reconstruction with a persisted projection table that is rebuilt by `import-db`, then verify the production-like benchmark improves on the same single-host stack.

**Architecture:** Add a new `lexicon.learner_catalog_entries` projection table owned by the import pipeline. Move learner range/list/search/adjacency/aggregate base queries onto that projection while keeping per-user learner status and detail hydration live. Rebuild the projection after lexicon import so it cannot drift from source rows.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, pytest, k6, Docker Compose

---

### Task 1: Add failing tests for projection-backed learner reads

**Files:**
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `backend/tests/test_words.py`

**Step 1: Write the failing tests**

Add tests that prove learner range/list/search/adjacency read from a projection model rather than rebuilding the old catalog CTE assumptions.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py backend/tests/test_words.py -q`
Expected: FAIL in the new projection-specific assertions.

**Step 3: Write minimal test scaffolding only**

Add only the smallest test fixtures/mocks needed to express the new projection contract.

**Step 4: Run test to verify it still fails for the right reason**

Run the same pytest command.
Expected: FAIL because production code still uses the old query path.

### Task 2: Add the projection model and migration

**Files:**
- Create: `backend/app/models/learner_catalog_entry.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/027_add_learner_catalog_projection.py`
- Modify: `backend/tests/test_models.py`

**Step 1: Write the failing model/migration test**

Add model coverage asserting the projection table shape and uniqueness assumptions.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py -q`
Expected: FAIL because the model and migration do not exist.

**Step 3: Write minimal implementation**

Add the projection model, register it, and create the Alembic revision with indexes aligned to rank, bucket, and search usage.

**Step 4: Run test to verify it passes**

Run the same pytest command.
Expected: PASS.

### Task 3: Add importer rebuild coverage first

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/import_db.py`

**Step 1: Write the failing test**

Add importer coverage proving a lexicon import rebuilds `learner_catalog_entries` deterministically from current words and phrases.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: FAIL because no rebuild exists yet.

**Step 3: Write minimal implementation**

Implement a full rebuild helper in `import_db.py` and call it from the successful import path.

**Step 4: Run test to verify it passes**

Run the same pytest command.
Expected: PASS.

### Task 4: Switch learner hot queries to the projection

**Files:**
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/api/words.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `backend/tests/test_words.py`

**Step 1: Write the failing tests**

Extend API/service tests so range/list/search/adjacency expect projection-backed behavior and live status joins.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py backend/tests/test_words.py -q`
Expected: FAIL because services still build the old CTE path.

**Step 3: Write minimal implementation**

Replace request-time catalog reconstruction with projection queries. Keep detail hydration on normalized source tables.

**Step 4: Run test to verify it passes**

Run the same pytest command.
Expected: PASS.

### Task 5: Rebuild benchmark fixture path and rerun focused verification

**Files:**
- Modify: `scripts/benchmark/run-single-host-benchmark.sh`
- Modify: `backend/tests/test_auth.py`
- Modify: `backend/tests/test_review_api.py`
- Modify: `backend/tests/test_lexicon_inspector_api.py`

**Step 1: Add only the necessary failing tests**

If the projection-backed read path changes fixture or benchmark setup assumptions, add the smallest failing coverage needed.

**Step 2: Run focused suites**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_auth.py backend/tests/test_review_api.py backend/tests/test_lexicon_inspector_api.py backend/tests/test_knowledge_map_api.py backend/tests/test_words.py backend/tests/test_models.py -q`
Expected: PASS after implementation.

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: PASS.

### Task 6: Rerun the production-like benchmark and update evidence

**Files:**
- Modify: `docs/reports/2026-03-27-single-host-capacity-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Run the benchmark**

Run: `./scripts/benchmark/run-single-host-benchmark.sh`
Expected: complete all configured stages and regenerate report artifacts.

**Step 2: Inspect the SQL exports**

Check the new `pg-stat-statements-top-total.csv` and `pg-stat-statements-top-mean.csv` for whether the old `knowledge_catalog_projection` family is gone or materially reduced.

**Step 3: Update docs/status**

Record the new benchmark evidence and the new dominant bottleneck, if any.

**Step 4: Run final scoped verification**

Run:
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_auth.py backend/tests/test_review_api.py backend/tests/test_lexicon_inspector_api.py backend/tests/test_knowledge_map_api.py backend/tests/test_words.py backend/tests/test_models.py -q`
- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`

Expected: PASS before claiming the slice is complete.
