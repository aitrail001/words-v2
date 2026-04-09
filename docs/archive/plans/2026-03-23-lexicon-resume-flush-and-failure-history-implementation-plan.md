# Lexicon Resume Flush And Failure History Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make realtime per-word lexicon enrichment flush completed lexemes to canonical artifacts immediately and preserve append-only failure history across resume attempts.

**Architecture:** Keep checkpoint as the authoritative completed skip ledger, but stop blocking canonical writes behind ordered flush gaps. Successful lexemes append directly to canonical output/decision/checkpoint artifacts when they finish. Failure rows remain append-only and are never reconciled away on resume or later success.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSONL ledgers, pytest/unittest.

---

### Task 1: Add failing tests for immediate canonical flush and append-only failure history

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write a failing flush test**

Cover:

- first lexeme fails
- second lexeme succeeds in the same invocation
- second lexeme is written immediately to `words.enriched.jsonl`, `enrich.decisions.jsonl`, and `enrich.checkpoint.jsonl`
- this must happen without waiting for process exit ordering cleanup

**Step 2: Write a failing resume history test**

Cover:

- pre-existing `enrich.failures.jsonl` row
- resume reruns that lexeme and fails again
- failure file contains both rows after the new run

**Step 3: Write a failing later-success test**

Cover:

- pre-existing failure row for a lexeme
- resume reruns it and succeeds
- checkpoint/decisions/output append success rows
- failure history remains intact
- a subsequent resume skips that lexeme because checkpoint contains it

**Step 4: Run the focused failing tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q -k "immediate or append_only or later_success"
```

Expected:

- the new tests fail before implementation

### Task 2: Remove ordered flush gating from per-word success persistence

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Replace buffered ordered success flush**

Change the per-word success path so a successful `run_word_job()` result is appended to canonical artifacts immediately.

**Step 2: Keep resume accounting correct**

Update `completed_lexeme_ids` and `max_new_completed_lexemes` tracking from those immediate appends.

**Step 3: Preserve failure summary behavior**

The invocation may still raise a summary failure if any lexemes failed, but successful later lexemes must already be durable before that point.

**Step 4: Run the focused tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q -k "immediate or later_success"
```

Expected:

- immediate flush tests pass

### Task 3: Make failure history append-only across resumes

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Stop failure reconciliation**

Remove logic that rewrites or deletes old failure rows on resume or later success.

**Step 2: Keep failure appends simple**

Every failed attempt appends one new row to `enrich.failures.jsonl`.

**Step 3: Run focused resume tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q -k "append_only or resume"
```

Expected:

- failure history tests pass

### Task 4: Update docs and status

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Document new artifact semantics**

Clarify:

- canonical files now flush on each successful lexeme
- checkpoint remains the resume skip ledger
- failures are append-only history

**Step 2: Record the fix in project status**

Include verification evidence and the live bug class addressed.

### Task 5: Verify before completion

**Files:**
- No new files expected

**Step 1: Run targeted lexicon tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q
```

**Step 2: Run full lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

**Step 3: Compile-check changed modules**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m py_compile tools/lexicon/enrich.py tools/lexicon/tests/test_enrich.py tools/lexicon/OPERATOR_GUIDE.md
```

Expected:

- focused tests pass
- full lexicon suite passes
- note that `py_compile` applies to Python modules only; docs should be verified by inspection rather than compilation
