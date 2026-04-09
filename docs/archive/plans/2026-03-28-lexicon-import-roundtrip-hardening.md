# Lexicon Import Round-Trip Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `import-db` practical for the full lexicon fixture, prove round-trip parity for translations and key compiled fields, and record the remaining normalization or loss explicitly.

**Architecture:** Keep the compiled JSONL contract unchanged while restructuring the importer around chunked streaming, chunk-local preloads, and safer parent/child persistence. Add a repeatable round-trip audit harness that compares source JSONL against exported JSONL from a fresh database and reports exact preservation vs normalization.

**Tech Stack:** Python, SQLAlchemy ORM, Postgres, pytest, Docker compose, lexicon CLI.

---

### Task 1: Add failing regression coverage for chunked/streamed import behavior

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing test**

Add tests that assert:
- the importer can consume rows from an iterator without requiring `list(rows)` semantics
- chunk commits occur on the configured boundary
- preloaded/new-row fast paths do not call existing-child loaders for brand-new parents

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: failing tests proving the current importer still assumes more expensive behavior.

**Step 3: Write minimal implementation**

Update `tools/lexicon/import_db.py` to pass only those failing tests.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: pass.

### Task 2: Optimize importer hot paths without changing semantics

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Write the failing test**

Add coverage for the specific safe optimizations:
- chunk-local preload lookup for words/phrases/references
- no guaranteed-miss child-loader calls for newly created word/meaning/enrichment rows
- relationship-safe parent/child creation where flushes can be deferred

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py -q`
Expected: fail on the new expectations.

**Step 3: Write minimal implementation**

Implement the importer optimizations while preserving behavior and FK correctness.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
Expected: pass.

### Task 3: Add round-trip compare harness for fixture parity

**Files:**
- Modify or create: `tools/lexicon/tests/test_cli.py` or `tools/lexicon/tests/test_roundtrip_export.py`
- Modify: `tools/lexicon/export_db.py` only if helper hooks are needed

**Step 1: Write the failing test**

Add regression coverage that imports the `smoke` fixture into a fresh DB, exports it, and compares:
- row identity counts
- top-level key presence
- translation locale/definition/example preservation
- known normalization cases such as empty `verb_forms`

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`
Expected: fail until the harness/reporting exists.

**Step 3: Write minimal implementation**

Implement the compare helpers and expected normalization rules.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
Expected: pass.

### Task 4: Execute real `full` fixture import->export->compare audit

**Files:**
- No source changes required unless defects are found
- Update: `docs/status/project-status.md`
- Optional create: `docs/plans/2026-03-28-lexicon-import-roundtrip-audit.md`

**Step 1: Run full-fixture audit on a fresh DB**

Run the importer/exporter against `tests/fixtures/lexicon-db/full/approved.jsonl` using a fresh Postgres DB and capture:
- import completion
- timing/progress evidence
- exported row counts
- missing key/translation diffs if any

**Step 2: If defects appear, add failing tests first**

Add the smallest regression test that proves the defect before changing implementation.

**Step 3: Fix defects and rerun the audit**

Repeat until the audit result is defensible.

### Task 5: Update live status with evidence and remaining caveats

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record verified outcomes**

Document:
- importer optimization result
- smoke/full round-trip findings
- exact translation parity result
- any remaining normalization caveats

**Step 2: Final verification**

Run the full relevant verification set:
- `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
- any additional backend/admin/E2E commands touched by the implementation

**Step 3: Report exact evidence**

Only then claim the slice is complete.

### Task 6: Throughput follow-up on phrase import and export hydration

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/export_db.py`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Optional create/modify: additional lexicon throughput regression tests
- Modify: `docs/status/project-status.md`

**Step 1: Write the failing regression tests**

Add coverage for:
- learner catalog projection rebuilds only once per full batched import
- phrase-path import avoids unnecessary per-child flush/read patterns where safe
- export avoids avoidable whole-table hydration work on the hottest paths

**Step 2: Run targeted tests to verify the new expectations fail or expose the current contract gaps**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
Expected: targeted failure or missing behavior before implementation.

**Step 3: Implement the minimal throughput changes**

Focus on:
- phrase import hot path
- export query/hydration path
- avoiding importer-side repeated whole-dataset work

**Step 4: Re-benchmark full fixture import and full round-trip**

Run the fresh-db `full` import timing again, then export and compare rows to prove correctness was preserved.

**Step 5: Update status with the new throughput result**

Record the new timing and parity evidence in `docs/status/project-status.md`.
