# Enrich CLI No-Abbrev Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make legacy `enrich --mode ...` fail loudly instead of being silently parsed as `--model ...`.

**Architecture:** Tighten `argparse` configuration so the `enrich` subparser also disables option abbreviation, then verify the real `argv=None` execution path with a regression test. Remove the now-brittle manual `--mode` rejection shim once the parser itself enforces exact flags.

**Tech Stack:** Python, argparse, unittest, lexicon CLI test harness

---

### Task 1: Add failing regression coverage

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write the failing test**

Add a test that patches `sys.argv` and calls `cli.main()` with no explicit argv list, passing `enrich --mode per_word`, and asserts the command exits non-zero with `unrecognized arguments: --mode per_word`.

**Step 2: Run test to verify it fails**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -k mode -q`

Expected: FAIL because the current subparser still abbreviates `--mode` to `--model`.

### Task 2: Tighten parser behavior

**Files:**
- Modify: `tools/lexicon/cli.py`

**Step 1: Write minimal implementation**

Configure subparsers to also use `allow_abbrev=False` and remove the manual `argv_list` guard once parser-level rejection works for both explicit argv lists and the real `sys.argv` path.

**Step 2: Run focused tests**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -k mode -q`

Expected: PASS

### Task 3: Verify the slice

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Record the change**

Add a brief status entry documenting that enrich now rejects stale `--mode` invocations directly via parser exact-match behavior.

**Step 2: Run broader verification**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`

Expected: PASS
