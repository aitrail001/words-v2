# Lexicon Suffix Hardening And Benchmark Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove bogus suffix-derived canonical links such as `pass -> pas` without regressing valid inflectional collapse, and expand the local benchmark sets used to validate canonicalization.

**Architecture:** Keep morphology-only canonical collapse as the main policy, but harden suffix-derived candidate generation so weak chopped stems are not treated as valid lexical targets without stronger evidence. Validate the fix with new regression tests and a broader family of local benchmark word lists that stress common tricky words, morphology-heavy words, semantic-ambiguity words, and additional suffix-risk buckets.

**Tech Stack:** Python 3.13, lexicon canonicalization/build-base pipeline, JSONL benchmark artifacts, pytest/unittest.

---

### Task 1: Add failing regression tests for bogus suffix stems

**Files:**
- Modify: `tools/lexicon/tests/test_canonical_forms.py`

**Steps:**
1. Add a failing test proving `pass` is not linked to `pas`.
2. Add one or more similar failing tests for short/double-letter suffix chops that should not survive as morphology-backed candidates.
3. Run the targeted canonical-forms test file and confirm the new tests fail.

### Task 2: Harden generic suffix-derived candidate handling

**Files:**
- Modify: `tools/lexicon/canonical_forms.py`

**Steps:**
1. Tighten suffix-derived candidate generation or downstream acceptance so weak stems like `pas` are filtered unless supported by stronger lexical evidence.
2. Preserve valid inflectional cases like `things -> thing`, `gives -> give`, `added -> add`, and `coming -> come`.
3. Keep morphology-linked standalone forms like `meeting -> meet` and `left -> leave`.
4. Re-run targeted tests and confirm the fix.

### Task 3: Expand benchmark word lists

**Files:**
- Create: `data/lexicon/benchmarks/*.txt`
- Create: `data/lexicon/benchmarks/*.json`
- Create: `data/lexicon/benchmarks/*.summary.json`

**Steps:**
1. Generate additional benchmark lists alongside the existing four benchmark artifacts.
2. Add at least one suffix-risk-oriented bucket to flush out bogus chopped stems.
3. Keep artifacts repo-local and deterministic.

### Task 4: Run build-base across benchmark sets and analyze outcomes

**Files:**
- Create: `data/lexicon/snapshots/*`
- Create: `data/lexicon/benchmarks/2026-03-13-*.md`

**Steps:**
1. Run `build-base` on all benchmark buckets without LLM enrichment.
2. Compare decision distributions, ambiguous tails, and known probe words.
3. Confirm the suspicious link class disappears and document any remaining issues.

### Task 5: Update status, verify, and prepare PR

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. Record the suffix-hardening outcome and benchmark evidence in the status board.
2. Run targeted tests plus the full lexicon suite.
3. Review the diff, commit the change set, open a PR, and merge if required checks pass.
