# Lexicon Learner Schema Evolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the next learner-facing schema slice so the local DB and enrichment inspection API can persist and expose richer lexicon fields already emitted by the offline pipeline.

**Architecture:** Keep the current offline lexicon ingestion path unchanged and evolve the storage boundary underneath it. Add nullable learner-facing columns to existing backend tables, update `import-db` to write them, and expand the read-only enrichment inspection endpoint to expose them for admin verification.

**Tech Stack:** Python CLI tooling, SQLAlchemy ORM, Alembic migrations, FastAPI, pytest/unittest, Docker-backed backend verification where needed.

---

## Task 1 — Reconfirm current compiled contract

1. Re-read `tools/lexicon/models.py`, `tools/lexicon/compile_export.py`, and `tools/lexicon/import_db.py`.
2. Reconfirm which learner-facing fields already exist in compiled rows but are not yet persisted.
3. Keep scope limited to existing compiled data; do not add new generation fields in this slice.

## Task 2 — Write failing backend model and API tests first

1. Add or extend tests for backend models covering the new learner-facing columns.
2. Extend `backend/tests/test_words.py` to assert the enrichment inspection endpoint returns the new word, meaning, and example fields.
3. Run the focused failing backend tests and confirm they fail for missing schema/model/API behavior.

## Task 3 — Write failing importer tests first

1. Extend `tools/lexicon/tests/test_import_db.py` to assert importer persistence for:
   - word-level `cefr_level`
   - word-level top-level POS
   - `confusable_words`
   - word-level learner `generated_at`
   - meaning-level sense metadata
   - example `difficulty`
2. Verify the focused importer tests fail before implementation.

## Task 4 — Add backend migration and model fields

**Files:**
- Create: `backend/alembic/versions/<next>_add_lexicon_learner_fields.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/meaning_example.py`
- Modify: `backend/app/models/__init__.py`

1. Add nullable learner-facing columns to `words`, `meanings`, and `meaning_examples`.
2. Prefer JSON columns for structured list fields already shaped as arrays/objects in compiled JSON.
3. Keep naming explicit and future-proof, avoiding collisions with existing generic columns.

## Task 5 — Implement importer write-through

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

1. Map top-level compiled row fields into `Word`.
2. Map per-sense learner metadata into `Meaning`.
3. Map per-example `difficulty` into `MeaningExample`.
4. Preserve current idempotent replace-by-source behavior for examples and relations.
5. Do not expand relation/table modeling beyond the already accepted current shape.

## Task 6 — Expand enrichment inspection API

**Files:**
- Modify: `backend/app/api/words.py`
- Test: `backend/tests/test_words.py`

1. Extend the Pydantic response models for word, meaning, and example enrichment details.
2. Return the newly persisted learner-facing fields from `GET /api/words/{word_id}/enrichment`.
3. Keep the smaller word-detail endpoint unchanged unless tests show a compelling need.

## Task 7 — Focused verification

1. Run focused lexicon importer tests.
2. Run focused backend lexicon model/API tests.
3. Run the full lexicon tool suite if focused tests pass.
4. If needed, run Docker-backed backend subset verification for the touched tests.
5. Record exact command output before claiming completion.

## Task 8 — Optional CI follow-up decision

1. Confirm whether this PR should only rely on existing CI jobs or also add a richer assertion set.
2. Keep CI scope tight unless missing coverage is directly tied to the new fields.
3. Defer broader live-Postgres import smoke additions unless they become necessary to safely land the schema slice.

## Task 9 — Update project status

1. Add a new row to `docs/status/project-status.md` once implementation is complete.
2. Record the verification evidence.
3. Note that phrase/idiom modeling and admin UI remain deferred.
