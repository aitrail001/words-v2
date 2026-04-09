# Legacy Learner JSON Drop and Phrase Cold-Path Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Drop duplicate learner JSON columns from hot lexicon tables and keep phrase provenance blobs off hot runtime paths.

**Architecture:** Runtime, admin, importer, and export flows will use only normalized child tables for learner POS/confusables/forms/meaning metadata/translation examples. A single migration then drops the duplicate JSON columns, while phrase routes keep `compiled_payload` as cold provenance by narrowing queries rather than removing the field entirely.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, pytest, Playwright, Docker Compose.

---

### Task 1: Prove runtime/admin/export/import no longer need legacy columns

**Files:**
- Modify: `backend/tests/test_words.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `backend/tests/test_lexicon_inspector_api.py`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_export_db.py`

**Step 1: Write/adjust failing tests**
- Make tests populate normalized child rows while legacy JSON values are stale or absent.
- Assert learner, inspector, importer, and export paths still return correct values.

**Step 2: Run focused tests to verify failures if legacy reads remain**
Run:
- `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_words.py backend/tests/test_knowledge_map_api.py backend/tests/test_lexicon_inspector_api.py -q`
- `PYTHONPATH=backend .venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_export_db.py -q`

**Step 3: Implement minimal fixes**
- Remove any remaining dependency on the legacy columns in the affected paths.

**Step 4: Re-run focused tests**
- Same commands as Step 2, now expecting pass.

### Task 2: Drop remaining duplicate-column reads/writes in production code

**Files:**
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/translation.py`
- Modify: `backend/app/api/words.py`
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/api/lexicon_inspector.py`
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/export_db.py`

**Step 1: Remove model columns and legacy references**
- Delete the six duplicate mapped columns.
- Remove fallback logic that references them.

**Step 2: Keep phrase hot paths narrow**
- Ensure learner/admin phrase detail queries use `load_only(...)` or projections that exclude `compiled_payload`.

**Step 3: Run focused backend and lexicon tests**
Run:
- `PYTHONPATH=backend .venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_words.py backend/tests/test_knowledge_map_api.py backend/tests/test_lexicon_inspector_api.py -q`
- `PYTHONPATH=backend .venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_export_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

### Task 3: Add the migration that drops duplicate columns

**Files:**
- Create: `backend/alembic/versions/026_drop_legacy_learner_json_columns.py`
- Modify: migration-sensitive tests if needed

**Step 1: Write migration-aware failing test where practical**
- Add/adjust tests that would fail if ORM/model/schema drift remains.

**Step 2: Write Alembic revision**
- Drop the six legacy columns.
- Downgrade recreates them as nullable JSON columns only if needed by project conventions.

**Step 3: Run targeted model/API/import/export tests again**
- Reuse Task 2 verification bundle.

### Task 4: Verify on rebuilt Docker stack

**Files:**
- No code changes expected unless regressions appear

**Step 1: Rebuild backend/worker against new migration**
Run:
- `NEXT_PUBLIC_API_URL=http://localhost:8000/api ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001,http://frontend:3000 docker compose -f docker-compose.yml up -d --build backend worker`

**Step 2: Check health**
Run:
- `curl -s http://localhost:8000/api/health`
Expected:
- `{"status":"ok","database":"ok","redis":"ok"}`

**Step 3: Run learner smoke**
Run:
- `docker compose -f docker-compose.yml exec -T playwright sh -lc "cd /workspace/e2e && E2E_BASE_URL=http://frontend:3000 E2E_API_URL=http://backend:8000/api E2E_DB_HOST=postgres E2E_DB_PASSWORD=change_this_password_in_production npm exec playwright test tests/smoke/knowledge-map.smoke.spec.ts --project=chromium"`

**Step 4: Fix regressions if any and rerun**

### Task 5: Update status and evidence

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Add dated status entries**
- Record duplicate-column removal and phrase cold-path verification evidence.

**Step 2: Summarize residual risks**
- Note whether `compiled_payload` remains intentionally for provenance/export only.
