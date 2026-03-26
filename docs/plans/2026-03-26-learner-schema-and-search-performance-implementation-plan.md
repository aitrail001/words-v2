# Learner Schema and Search Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce learner/search latency and row width by moving hot search onto index-friendly query shapes, retiring duplicate learner JSON compatibility fields, and hardening lexicon fixtures/tests for aligned localized example translations.

**Architecture:** The backend will search base word/phrase tables using trigram-backed predicates before projecting learner catalog rows, while normalized child tables become the only canonical source for forms/confusables/meaning metadata/translation examples. Fixture artifacts and importer tests will be upgraded so the test corpus reflects the multi-example translation contract already enforced by the schemas.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL (`pg_trgm`, GIN), Alembic, pytest, JSONL fixtures.

---

### Task 1: Add search indexes and migrate schema

**Files:**
- Modify: `backend/alembic/versions/...` (new migration)
- Modify: `docs/status/project-status.md`

**Steps:**
1. Add an Alembic migration that enables `pg_trgm` and creates GIN trigram indexes for `lexicon.words.word`, `lexicon.phrase_entries.normalized_form`, and `lexicon.phrase_entries.phrase_text`.
2. Keep existing equality/FK indexes unchanged.
3. Record the schema change in status after verification.

### Task 2: Rework hot search queries

**Files:**
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/words.py`
- Test: `backend/tests/test_knowledge_map_api.py`
- Test: `backend/tests/test_words.py`

**Steps:**
1. Change learner search to filter words and phrases on base tables before projection/union.
2. Preserve current response ordering semantics.
3. Keep exact word lookup unchanged.
4. Add tests for result parity and route-level behavior.

### Task 3: Retire duplicate learner JSON compatibility fields

**Files:**
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/app/api/words.py`
- Modify: `tools/lexicon/import_db.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/translation.py`
- Test: `tools/lexicon/tests/test_import_db.py`
- Test: `backend/tests/test_words.py`
- Test: `backend/tests/test_knowledge_map_api.py`

**Steps:**
1. Stop runtime shaping from falling back to legacy JSON for forms/confusables/meaning metadata/translation examples.
2. Stop `import-db` from writing those legacy JSON columns.
3. Keep `phonetics` unchanged.
4. Add tests that prove normalized child rows are the source of truth.

### Task 4: Harden lexicon fixture artifacts and importer regressions

**Files:**
- Modify: `tests/fixtures/lexicon-db/smoke/approved.jsonl`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_translations_pipeline.py`

**Steps:**
1. Update the smoke fixture so at least one word and one phrase row contain two English examples with aligned localized example arrays.
2. Add or tighten importer/tests asserting two-example localized translation preservation.
3. Keep fixture rows minimal but contract-valid.

### Task 5: Verify and update status

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. Run scoped backend, lexicon, and any affected Docker smoke verification.
2. Update the canonical status doc with exact evidence.
