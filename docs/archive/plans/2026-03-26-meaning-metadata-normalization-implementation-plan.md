# Meaning Metadata Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize `lexicon.meanings.secondary_domains` and `lexicon.meanings.grammar_patterns` into structured child rows while preserving safe JSON fallback during transition.

**Architecture:** Add one generic `lexicon.meaning_metadata` child table keyed by meaning, metadata kind, and order index. Keep the existing JSON columns as transition fallback, update importer replacement semantics to own the normalized rows, and make learner/word-detail reads prefer normalized rows first.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Postgres, pytest

---

### Task 1: Pin normalized meaning-metadata behavior with tests

**Files:**
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `backend/tests/test_words.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

Add regressions proving:

1. aggregate model import exposes `MeaningMetadata`
2. learner word detail prefers normalized meaning metadata over stale JSON arrays
3. word enrichment detail prefers normalized meaning metadata over stale JSON arrays
4. importer replaces normalized meaning metadata rows on reimport

### Task 2: Implement normalized storage and fallback reads

**Files:**
- Create: `backend/app/models/meaning_metadata.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/023_add_meaning_metadata.py`
- Modify: `backend/app/services/knowledge_map.py`

Add a generic meaning-metadata model with:

- `meaning_id`
- `metadata_kind`
- `value`
- `order_index`

and a helper that reconstructs `secondary_domains` plus `grammar_patterns` from normalized rows first, then falls back to legacy JSON.

### Task 3: Update read paths and importer ownership

**Files:**
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/api/words.py`
- Modify: `tools/lexicon/import_db.py`

1. eager-load `Meaning.metadata_entries` in the word-detail/read paths
2. replace normalized meaning metadata rows on import/reimport
3. keep legacy JSON columns updated during transition

### Task 4: Verify and update status

**Files:**
- Modify: `docs/status/project-status.md`

Run:

- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_knowledge_map_api.py backend/tests/test_words.py -q`
- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q -k 'meaning_metadata or translation_example or word_form or confusable'`

Record the slice and evidence in the status board.
