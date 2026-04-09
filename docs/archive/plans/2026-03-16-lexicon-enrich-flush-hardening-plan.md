# Lexicon Enrich Flush Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add durable immediate success logging for per-word enrichment so large concurrent runs do not appear stalled on disk when later lexemes finish before an earlier ordered gap clears.

**Architecture:** Keep the current ordered canonical files for compatibility, but add a new append-only raw-completion ledger that writes as soon as a lexeme finishes successfully. On resume, reconcile that raw ledger so successful-but-not-yet-canonicalized lexemes are not lost after interruption.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSONL artifacts, pytest/unittest.

---

### Task 1: Add failing tests for the hidden-progress durability gap

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write a failing test for out-of-order completion durability**

Cover:

- one earlier lexeme delayed
- one later lexeme completes first
- new raw completion ledger writes immediately even before canonical ordered flush can advance

**Step 2: Write a failing resume test**

Cover:

- raw completion ledger contains a success not yet reflected in canonical checkpoint/output
- resume reconciles that success instead of rerunning or losing it

**Step 3: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- new tests fail before implementation

### Task 2: Add raw completion ledger support to per-word enrichment

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Introduce a new artifact path**

Use a standard snapshot-side filename such as:

- `enrich.completed.raw.jsonl`

**Step 2: Append successful lexeme completions immediately**

Write a row as soon as a lexeme completes successfully, before waiting for ordered canonical flush to advance.

**Step 3: Keep existing ordered canonical files**

Do not change the existing semantics of:

- `enrichments.jsonl`
- `enrich.checkpoint.jsonl`

in this first hardening slice.

**Step 4: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- raw completion ledger tests pass

### Task 3: Reconcile raw completions on resume

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Add resume reconciliation from raw completion ledger**

When resuming:

- load raw-completed lexemes not yet reflected in canonical checkpoint/output
- safely fold them back into the canonical artifact set
- avoid rerunning those lexemes unnecessarily

**Step 2: Preserve active-failure semantics**

Keep `enrich.failures.jsonl` as the active unresolved failure ledger only.

**Step 3: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected:

- resume reconciliation tests pass

### Task 4: Expose and document the new ledger behavior

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md` if rollout guidance changes materially

**Step 1: Document artifact semantics**

Explain:

- `enrich.checkpoint.jsonl` is canonical completed progress
- `enrich.failures.jsonl` is active unresolved failures
- `enrich.completed.raw.jsonl` is the immediate success ledger for durability during concurrent runs

**Step 2: Document operator interpretation**

Explain that flat canonical checkpoint growth does not necessarily mean zero useful work if raw completion rows are still increasing.

### Task 5: Verification before completion

**Files:**
- No new files expected

**Step 1: Run the focused enrichment suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q
```

**Step 2: Optionally run a bounded local smoke**

Use a small placeholder or real smoke snapshot to confirm:

- raw completion ledger grows immediately
- canonical checkpoint may lag but later reconciles
- resume keeps successful lexemes

**Step 3: Report operational impact**

Call out:

- what changed in artifact semantics
- whether current live 30K run should adopt the new logic immediately or after a controlled restart
