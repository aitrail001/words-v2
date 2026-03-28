# Lexicon Bulk Child Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce the remaining full-fixture import time by replacing the hottest row-by-row child inserts with chunk-local bulk writes while preserving exact import->export round-trip parity.

**Architecture:** Keep parent entry creation on the current ORM path so the import contract and update semantics stay stable. After parent IDs exist for a chunk, collect child rows for the hot lexicon tables and write them with SQLAlchemy Core bulk `insert()` calls, then continue using the current export and round-trip compare path to prove parity.

**Tech Stack:** Python, SQLAlchemy ORM/Core, PostgreSQL, pytest, lexicon CLI.

---

### Task 1: Lock the expected importer behavior with tests

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Test: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write/adjust failing tests**
- Add targeted tests that prove the importer uses chunk-local bulk insert for the selected hot child tables instead of `session.add()` per row.
- Cover at least `MeaningExample`, `TranslationExample`, and `WordRelation` when the session/model stack supports SQLAlchemy Core bulk execution.

**Step 2: Run targeted test to verify the old path fails the new expectation**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q -k 'bulk_child_insert'`
Expected: FAIL on the pre-change importer path.

**Step 3: Keep tests narrow**
- Assert interaction shape and inserted payload semantics, not full benchmark numbers.

**Step 4: Re-run the targeted test after implementation**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q -k 'bulk_child_insert'`
Expected: PASS.

### Task 2: Implement chunk-local bulk child inserts

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Possibly modify: `backend/app/models/meaning_example.py`
- Possibly modify: `backend/app/models/translation_example.py`
- Possibly modify: `backend/app/models/word_relation.py`

**Step 1: Add importer helpers**
- Add small helpers to detect when a model/session combination supports Core bulk insert safely.
- Add helpers to normalize row payloads for chunk-local insert batches.

**Step 2: Implement minimal bulk path**
- Keep ORM parent creation for `Word`, `Meaning`, phrase graph, and translation parents.
- Replace row-by-row child insertion with chunk-local `session.execute(insert(model), rows)` where safe.
- Start with the hottest tables only.

**Step 3: Preserve current update semantics**
- Bulk path must still respect delete/replace logic for existing child rows.
- New path must preserve ordering, `source`, `confidence`, and enrichment linkage fields.

**Step 4: Keep fallback path**
- If fake test models or non-Core-compatible models are supplied, keep the existing per-row fallback.

### Task 3: Verify parity stays exact

**Files:**
- Modify if needed: `tools/lexicon/roundtrip_compare.py`
- Test: `tools/lexicon/tests/test_roundtrip_compare.py`

**Step 1: Keep round-trip compare contract intact**
- No new normalization exceptions unless required and justified.

**Step 2: Run targeted lexicon test suite**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_export_db.py tools/lexicon/tests/test_roundtrip_compare.py tools/lexicon/tests/test_cli.py -q`
Expected: PASS.

### Task 4: Benchmark and verify on the full fixture

**Files:**
- No new files unless benchmark notes require docs updates.

**Step 1: Prepare a fresh benchmark DB**
- Create a fresh Postgres database.
- Run Alembic head.

**Step 2: Run full import benchmark**

Run: `/usr/bin/time -p env DATABASE_URL=... DATABASE_URL_SYNC=... PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli import-db --input tests/fixtures/lexicon-db/full/approved.jsonl --source-type repo_fixture --source-reference full-roundtrip --log-level quiet`
Expected: complete faster than the current `169.36s` baseline.

**Step 3: Run export benchmark**

Run: `/usr/bin/time -p env DATABASE_URL=... DATABASE_URL_SYNC=... PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli export-db --output /tmp/<file>.jsonl`
Expected: no regression from the current `10.98s` baseline.

**Step 4: Run round-trip compare**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -c "... compare_compiled_rows(...) ..."`
Expected: exact row/key/translation parity.

### Task 5: Document the retained result

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record the measured outcome**
- If the new bulk path wins, update status with the new numbers and scope.
- If it is a wash or regression, document that and keep the faster baseline.

**Step 2: Keep the note precise**
- Include exact commands, DB names, and parity counts.
