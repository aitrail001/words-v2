# Import DB Conflict Modes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `tools.lexicon.cli import-db` safe and explicit when importing into a non-empty DB by fixing existing-word child replacement and adding `fail|upsert|skip` conflict modes.

**Architecture:** Keep the current importer as the canonical path, but route each compiled row through a conflict policy before mutating the DB. `upsert` will update existing normalized children without premature autoflush, `skip` will leave existing entries untouched, and `fail` will preserve strict validation behavior. CLI and tests will expose the policy explicitly.

**Tech Stack:** Python, SQLAlchemy ORM, argparse CLI, unittest/pytest for `tools/lexicon`.

---

### Task 1: Add failing tests for re-import conflict handling

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing importer tests**
- Add a focused unit test showing an existing word with normalized child rows can be re-imported in `upsert` mode without duplicate child-row insertion semantics.
- Add a focused unit test showing `skip` leaves the existing word unchanged and counts a skipped row.
- Add a focused unit test showing `fail` raises on an existing word.

**Step 2: Write failing CLI test**
- Add a CLI parser/handler test for `import-db --on-conflict upsert|skip|fail` and confirm the selected mode is forwarded into `run_import_file()`.

**Step 3: Run the narrow test subset and confirm red**
Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
Expected: fail on the new assertions because the mode plumbing/behavior does not exist yet.

### Task 2: Implement importer conflict modes and safe existing-row sync

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/cli.py`

**Step 1: Add explicit conflict mode plumbing**
- Extend `run_import_file()` and `import_compiled_rows()` with `on_conflict='fail'|'upsert'|'skip'`.
- Default CLI to `upsert` for operator/dev imports; keep strict behavior available via `fail`.

**Step 2: Implement policy decisions per entry**
- For word rows, when an existing word is found:
  - `fail`: raise a deterministic conflict error before mutating.
  - `skip`: do not mutate the entry or children; record a skipped count.
  - `upsert`: continue into safe update path.
- Apply the same policy shape to phrase/reference rows for consistency where existing normalized-form matches occur.

**Step 3: Fix premature autoflush during normalized child replacement**
- Guard existing-row mutation/query boundaries with `session.no_autoflush` where replacement of child collections can otherwise flush partially updated state.
- Keep normalized child replacement deterministic for confusables/forms/POS and other existing-word children.

### Task 3: Verify and report

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run targeted verification**
Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`
Expected: pass.

**Step 2: Optionally run the smallest live repro if needed**
- Re-run the failing import scenario against the dev stack with `--on-conflict upsert` only if unit tests are insufficient to prove the bug is fixed.

**Step 3: Update live status**
- Add a short status entry in `docs/status/project-status.md` with the new import conflict behavior and fresh verification evidence.
