# Enrich Resume Failed Modes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--skip-failed` and `--retry-failed-only` to realtime `enrich` so resume can skip unresolved failures or run only unresolved failures, while keeping append-only failure history and deduping retry scheduling by `lexeme_id`.

**Architecture:** Keep checkpoint JSONL as the source of truth for completed lexemes and keep the failure JSONL append-only for history. Derive unresolved failures at runtime as `failed lexeme IDs - completed lexeme IDs`, then filter pending lexemes according to the chosen resume mode. Mirror the validated operator semantics already used by `voice-generate`, but keep the richer append-only failure history that `enrich` already relies on.

**Tech Stack:** Python, argparse CLI, JSONL ledgers, pytest/unittest, existing lexicon runtime logger.

---

### Task 1: Add failing CLI tests for invalid flag combinations

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Write the failing tests**

Add tests that assert `enrich` rejects:

```python
--retry-failed-only
--skip-failed
--resume --retry-failed-only --skip-failed
```

with stderr messages indicating the invalid combination.

**Step 2: Run test to verify it fails**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`
Expected: FAIL in the new enrich CLI flag tests because the parser/handler does not know these flags yet.

**Step 3: Write minimal implementation**

In `tools/lexicon/cli.py`:
- add `enrich.add_argument('--retry-failed-only', action='store_true', ...)`
- add `enrich.add_argument('--skip-failed', action='store_true', ...)`
- in the enrich command handler, reject:
  - retry-only without resume
  - skip-failed without resume
  - retry-only with skip-failed

**Step 4: Run test to verify it passes**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q`
Expected: PASS for the new CLI tests.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_cli.py tools/lexicon/cli.py
git commit -m "test(enrich): cover resume retry flag validation"
```

### Task 2: Add failing enrich scheduling tests for the three resume modes

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write the failing tests**

Add tests that prove:
- `resume=True` retries unresolved failed lexemes by default
- `resume=True, skip_failed=True` excludes unresolved failed lexemes
- `resume=True, retry_failed_only=True` schedules only unresolved failed lexemes

Use the existing snapshot fixture style in `test_enrich.py` and record called lemmas from the provider.

**Step 2: Run test to verify it fails**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: FAIL because `enrich_snapshot()` has no `skip_failed` or `retry_failed_only` behavior.

**Step 3: Write minimal implementation**

In `tools/lexicon/enrich.py`:
- add `retry_failed_only: bool = False` and `skip_failed: bool = False` to `enrich_snapshot()` and `run_enrichment()`
- add a helper that loads failed `lexeme_id`s from `enrich.failures.jsonl`
- derive unresolved failure IDs by subtracting completed checkpoint IDs
- update `pending_lexemes` selection:
  - resume: `not completed`
  - resume + skip_failed: `not completed and not unresolved_failed`
  - resume + retry_failed_only: `in unresolved_failed`

**Step 4: Run test to verify it passes**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: PASS for the new resume scheduling tests.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_enrich.py tools/lexicon/enrich.py tools/lexicon/cli.py
git commit -m "feat(enrich): add failed resume scheduling modes"
```

### Task 3: Add failing dedupe and append-only-history regression tests

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write the failing tests**

Add tests that prove:
- `retry_failed_only` dedupes multiple failure rows for the same `lexeme_id`
- a later success does not delete prior failure rows
- resolved failures are excluded from `retry_failed_only` if the lexeme is already in the checkpoint ledger

Use explicit pre-written `enrich.failures.jsonl` and `enrich.checkpoint.jsonl` rows.

**Step 2: Run test to verify it fails**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: FAIL in the new dedupe/resolved-failure regression tests.

**Step 3: Write minimal implementation**

In `tools/lexicon/enrich.py`:
- make the failure loader return a `set[str]` of failed `lexeme_id`s
- do not rewrite or trim `enrich.failures.jsonl`
- ensure unresolved failure IDs are always `failed_ids - completed_ids`

**Step 4: Run test to verify it passes**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: PASS for the new dedupe/history tests.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_enrich.py tools/lexicon/enrich.py
git commit -m "test(enrich): cover failed retry dedupe semantics"
```

### Task 4: Document the operator behavior

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write the doc updates**

Add `enrich` resume option documentation to `tools/lexicon/README.md`:
- `--resume`
- `--resume --skip-failed`
- `--resume --retry-failed-only`
- clarify append-only failure history and unresolved-failure derivation

Add a concise status-log entry with fresh verification evidence to `docs/status/project-status.md`.

**Step 2: Run focused verification**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q`
Expected: PASS.

**Step 3: Commit**

```bash
git add tools/lexicon/README.md docs/status/project-status.md
git commit -m "docs(enrich): document failed resume modes"
```

### Task 5: Final verification and branch completion

**Files:**
- Review only changed files from previous tasks

**Step 1: Run final verification**

Run: `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q`
Expected: PASS with the full focused slice green.

**Step 2: Report exact evidence**

Capture the pass counts and any warnings verbatim for the handoff.

**Step 3: Complete development branch**

Use `superpowers:finishing-a-development-branch` after verification succeeds.
