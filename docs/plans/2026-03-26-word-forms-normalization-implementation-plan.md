# Word Forms Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize `lexicon.words.word_forms` into structured child rows while preserving safe JSON fallback during transition.

**Architecture:** Add one generic `lexicon.word_forms` child table keyed by `word_id`, `form_kind`, `form_slot`, and `order_index`. Keep the existing JSON column as provenance/transition fallback, update importer replacement semantics to own the normalized rows, and make learner helpers reconstruct the current response shape from normalized rows first.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Postgres, pytest

---

### Task 1: Pin normalized word-form behavior with tests

**Files:**
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_knowledge_map_api.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Model regression**

Add a model-registry test proving the aggregate model import path exposes the normalized word-form model and `Word(...).form_entries` defaults to `[]`.

**Step 2: API regression**

Add a learner detail/API regression proving `normalize_word_forms(...)` prefers normalized child rows over legacy `word.word_forms` JSON and reconstructs:

- `verb_forms`
- `plural_forms`
- `derivations`
- `comparative`
- `superlative`

**Step 3: Import regression**

Add an importer regression proving repeated imports replace normalized word-form child rows rather than accumulating stale forms.

**Step 4: Verify tests fail for the intended reason**

Run:

`PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_knowledge_map_api.py -q`

and

`/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q -k word_form`

Expected: fail until implementation lands.

### Task 2: Implement normalized word-form storage and fallback reads

**Files:**
- Create: `backend/app/models/word_form.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/021_add_word_forms.py`
- Modify: `backend/app/services/knowledge_map.py`

**Step 1: Add model + relationship**

Create a normalized `lexicon.word_forms` model with:

- `word_id`
- `form_kind`
- `form_slot`
- `value`
- `order_index`

and add `Word.form_entries`.

**Step 2: Add migration**

Create/backfill the new table from legacy JSON `words.word_forms`.

**Step 3: Update read helper**

Make `normalize_word_forms(...)` prefer normalized child rows and only fall back to `word.word_forms` JSON when needed.

### Task 3: Update importer ownership of normalized word forms

**Files:**
- Modify: `tools/lexicon/import_db.py`

**Step 1: Extend default model loading**

Expose the normalized word-form model in `_default_models()`.

**Step 2: Add sync helper**

Translate compiled `forms` payload into normalized child rows and replace the collection on import/reimport.

**Step 3: Keep JSON fallback intact**

Continue storing `word.word_forms` during transition so non-migrated readers remain safe.

### Task 4: Verify and update status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run focused verification**

Run:

- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_knowledge_map_api.py -q`
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_words.py -q`
- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q -k 'word_form or confusable'`

**Step 2: Record status**

Update `docs/status/project-status.md` with the normalized word-form slice and fresh evidence.
