# Lexicon Sense-Era Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove sense-era and staged-selection legacy flows so the lexicon tool and admin portal operate on lexeme-only enrichment and compiled-artifact review paths only.

**Architecture:** The cleanup makes `lexemes.jsonl` the only base enrichment input, preserves realtime direct writes to `words.enriched.jsonl`, keeps batch as request/result ingest with the same word-level QC/materialization, and removes WordNet/sense-selection/staged-selection review contracts from tooling, backend ops metadata, and admin portal surfaces.

**Tech Stack:** Python CLI tooling, FastAPI backend, Next.js admin frontend, Playwright E2E, pytest, Jest.

---

### Task 1: Freeze the target contract in tests

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_unified_enrichment_flow.py`
- Modify: `backend/tests/test_lexicon_ops_api.py`
- Modify: `admin-frontend/src/app/lexicon/ops/__tests__/page.test.tsx`
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`

**Step 1: Write failing assertions for the new contract**
- `build-base` no longer emits `senses.jsonl` or `concepts.jsonl`
- realtime enrich succeeds with `lexemes.jsonl` only
- batch ingest/materialization does not require `senses.jsonl`
- ops/admin no longer mention `selection_decisions.jsonl` or `compile-export`

**Step 2: Run the targeted tests to capture current failures**
- Lexicon pytest slices
- Backend ops tests
- Admin ops Jest tests
- Targeted Playwright smoke discovery/run where feasible

### Task 2: Remove sense-era snapshot dependencies from the tool

**Files:**
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/validate.py`
- Modify: `tools/lexicon/canonical_registry.py`
- Modify: `tools/lexicon/tests/*` affected by snapshot fixtures

**Step 1: Make `write_base_snapshot` lexeme-only for enrichment inputs**
- stop writing `senses.jsonl` and `concepts.jsonl`
- keep canonicalization/operator files still in active use

**Step 2: Remove runtime reads of `senses.jsonl`**
- make enrich snapshot input loading lexeme-only
- remove compile/materialization dependence on base senses

**Step 3: Keep batch compatible with lexeme-only snapshots**
- ensure batch ingest/shared QC works from results + lexeme metadata only

### Task 3: Remove selection/rerank/staged-review legacy CLI and artifact flows

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `tools/lexicon/docs/batch.md`
- Modify: `backend/app/api/lexicon_ops.py`
- Modify: `backend/tests/test_lexicon_ops_api.py`

**Step 1: Remove obsolete CLI commands and references**
- remove sense rerank / compare-selection / score-selection-risk / prepare-review flows from the active surface
- keep only flows required by current realtime/batch design

**Step 2: Simplify snapshot ops metadata**
- remove `selection_decisions` counts/flags
- update operator hints from `compile-export`/selection review to compiled review and JSONL review only

### Task 4: Remove staged selection review from backend and admin portal

**Files:**
- Modify: `backend/app/api/lexicon_reviews.py`
- Modify: `backend/tests/test_lexicon_reviews_api.py`
- Modify: `backend/tests/test_lexicon_review_publish_api.py`
- Modify: `backend/tests/test_lexicon_review_models.py`
- Modify: `admin-frontend/src/app/lexicon/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/legacy/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts`

**Step 1: Remove `selection_decisions.jsonl` upload/review UI and backend assumptions**
- the portal should no longer present that path as current or supported
- keep compiled-review and JSONL-review as the review surfaces

**Step 2: Update labels/help text/import guidance**
- direct users to reviewed compiled artifacts and DB import only

### Task 5: Update docs, status, and full verification

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: any affected docs from Tasks 2-4

**Step 1: Update status and operator docs**
- record that sense-era and staged-selection paths were removed
- record the new canonical artifact flow

**Step 2: Run verification**
- `/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
- `PYTHONPATH=backend /.venv-backend/bin/python -m pytest backend/tests -q`
- `npm test -- --runInBand` or targeted admin frontend tests for changed pages
- targeted Playwright smoke(s) covering ops/review/import flow

**Step 3: Summarize residual risk**
- call out any intentionally deferred legacy cleanup or migration edges
