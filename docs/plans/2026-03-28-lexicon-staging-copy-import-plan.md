# Lexicon Staging COPY Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Postgres-first `COPY`/staging import mode that materially beats the current `164.70s` full-fixture baseline while preserving exact export round-trip parity.

**Architecture:** Keep the current ORM importer as a fallback mode and build a new `staging` mode that streams compiled JSONL into raw staging, normalizes into typed staging tables, and merges into lexicon tables with set-based SQL. Start with the word-path staging slice first, then extend to phrases.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL, Alembic, pytest, lexicon CLI.

---

### Task 1: Add the first failing tests for staging-mode entry points

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write failing CLI/import tests**
- Add tests for `--import-mode staging` plumbing.
- Add importer tests that assert staging mode delegates to a staging-path implementation instead of the ORM importer.

**Step 2: Run the targeted tests and verify they fail**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_import_db.py -q -k 'import_mode_staging or staging_import'`
Expected: FAIL before implementation.

### Task 2: Add staging schema and import run scaffolding

**Files:**
- Modify/Create: `backend/alembic/versions/<new>_add_lexicon_staging_tables.py`
- Modify/Create: `tools/lexicon/staging_import.py`
- Modify: `tools/lexicon/import_db.py`

**Step 1: Add staging tables**
- Create raw + typed staging tables for the first word-path slice.
- Include `import_run_id` and natural keys.

**Step 2: Add staging helper module**
- raw row ingest helper
- normalize helper
- set-based merge helper
- cleanup helper

**Step 3: Wire import mode**
- `run_import_file(..., import_mode='orm'|'staging')`
- CLI `import-db --import-mode`

### Task 3: Implement the first set-based word-path merge slice

**Files:**
- Modify/Create: `tools/lexicon/staging_import.py`
- Modify: `tools/lexicon/import_db.py`
- Modify tests as needed

**Step 1: Raw staging ingest**
- stream JSONL rows into raw staging

**Step 2: Normalize typed staging rows for words**
- words
- meanings
- meaning examples
- translations
- translation examples
- word relations

**Step 3: Merge into lexicon tables with SQL**
- words first
- meanings second
- child replacements third

**Step 4: Keep fallback intact**
- `orm` path unchanged unless needed for shared helpers

### Task 4: Verify parity for the word-path staging slice

**Files:**
- Modify if needed: `tools/lexicon/tests/test_roundtrip_compare.py`

**Step 1: Run lexicon test slice**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_roundtrip_compare.py -q`
Expected: PASS.

**Step 2: Run fresh DB import/export/compare**
- benchmark word-path staging import on the full fixture
- verify parity stays exact for the rows covered by the new path

### Task 5: Extend staging merge to phrases

**Files:**
- Modify/Create: `tools/lexicon/staging_import.py`
- Modify tests

**Step 1: Add phrase staging tables/normalization**
- phrase entries
- senses
- localizations
- examples
- example localizations

**Step 2: Add phrase merge SQL**
- replace phrase child graph set-based for touched entries

**Step 3: Re-run full round-trip**
- import
- export
- compare

### Task 6: Benchmark and document retained result

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run full benchmark on fresh DB**
- staging import benchmark
- export benchmark
- compare result

**Step 2: Update status**
- document exact timings and parity evidence
- if staging loses or is incomplete, document that precisely and keep the faster retained path
