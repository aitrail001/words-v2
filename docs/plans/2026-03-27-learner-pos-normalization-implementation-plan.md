# Learner POS Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize learner word part-of-speech storage into structured rows and switch runtime reads/writes onto the normalized contract.

**Architecture:** Add `lexicon.word_part_of_speech` rows with migration backfill, update importer replacement semantics, and make learner/admin APIs eager-load and shape POS from normalized rows instead of JSON arrays.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, repo-local lexicon importer tests.

---

### Task 1: Add normalized POS schema

**Files:**
- Create: `backend/app/models/word_part_of_speech.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/025_add_word_part_of_speech.py`
- Test: `backend/tests/test_models.py`

**Steps:**
1. Write failing model/migration test expectations for normalized POS rows.
2. Add model + relationship.
3. Add Alembic migration with backfill from `words.learner_part_of_speech`.
4. Run focused backend tests.

### Task 2: Update importer write path

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

**Steps:**
1. Write failing importer tests for replacing normalized POS rows.
2. Add `_sync_word_part_of_speech_rows(...)`.
3. Wire it into word upsert path.
4. Run focused lexicon tests.

### Task 3: Switch learner/admin reads

**Files:**
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/api/words.py`
- Test: `backend/tests/test_knowledge_map_api.py`
- Test: `backend/tests/test_words.py`

**Steps:**
1. Write failing tests showing normalized POS beats stale JSON.
2. Add normalization helper over `word.part_of_speech_entries`.
3. Eager-load POS rows on hot paths.
4. Update API shaping.
5. Run focused backend tests.

### Task 4: Verification and docs

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. Run backend + lexicon focused verification.
2. Record evidence in status board.
3. Leave legacy JSON column removal for a later slice.
