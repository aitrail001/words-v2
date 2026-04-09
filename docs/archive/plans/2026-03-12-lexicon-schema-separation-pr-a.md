# Lexicon Schema Separation PR A Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move lexicon-owned persistence into a dedicated Postgres `lexicon` schema while preserving current backend behavior and lexicon import tooling.

**Architecture:** Keep one Postgres database/server, but move lexicon reference-data and lexicon pipeline tables into schema `lexicon`. Runtime tables remain in the default schema. Update SQLAlchemy models and foreign keys to be schema-aware, add one forward migration that creates `lexicon` and moves the existing tables, and verify backend/import paths continue to work.

**Tech Stack:** Python 3.13, SQLAlchemy ORM, Alembic, PostgreSQL schema DDL, pytest.

---

### Task 1: Add failing tests for schema-aware lexicon models

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Create/Modify: `backend/tests/test_lexicon_schema_config.py`

**Steps:**
1. Add a small test that asserts lexicon-owned ORM models report schema `lexicon`.
2. Add a small import-db test that exercises schema-qualified SQLAlchemy models if needed.
3. Run targeted tests and confirm failure before implementation.

### Task 2: Make lexicon-owned models schema-aware

**Files:**
- Create: `backend/app/models/schema_names.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/translation.py`
- Modify: `backend/app/models/meaning_example.py`
- Modify: `backend/app/models/word_relation.py`
- Modify: `backend/app/models/lexicon_enrichment_job.py`
- Modify: `backend/app/models/lexicon_enrichment_run.py`
- Modify: `backend/app/models/lexicon_review_batch.py`
- Modify: `backend/app/models/lexicon_review_item.py`
- Modify: `backend/app/models/review.py`
- Modify: `backend/app/models/word_list_item.py`

**Steps:**
1. Add a single lexicon schema constant/helper.
2. Set `__table_args__` schema for lexicon-owned tables.
3. Update internal lexicon foreign keys to `lexicon.<table>.id`.
4. Update runtime-to-lexicon foreign keys similarly.
5. Keep relationship names and API behavior unchanged.

### Task 3: Add migration to create/move schema

**Files:**
- Create: `backend/alembic/versions/010_move_lexicon_tables_to_lexicon_schema.py`

**Steps:**
1. Create `lexicon` schema if missing.
2. Move lexicon-owned tables with `ALTER TABLE ... SET SCHEMA lexicon` in dependency-safe order.
3. Make downgrade move them back to `public`.
4. Preserve existing data and constraints.

### Task 4: Verify tool/backend import paths still work

**Files:**
- Modify: `tools/lexicon/import_db.py` only if needed
- Modify: docs if behavior/ops change

**Steps:**
1. Run targeted lexicon import tests.
2. Run targeted backend tests touching words/reviews if needed.
3. Verify no schema-specific config changes are required for normal local use.

### Task 5: Update operator docs and project status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Document that lexicon content now lives under `lexicon` schema.
2. Clarify that runtime/app tables remain separate in the same database.
3. Add verification evidence to the status board.

### Task 6: Verify, commit, PR, merge, clean up

**Verification:**
- Targeted lexicon tests
- Targeted backend tests for lexicon/review paths
- Alembic/YAML syntax sanity if touched
- Fresh git diff review before commit
