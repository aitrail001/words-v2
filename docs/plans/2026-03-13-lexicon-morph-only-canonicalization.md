# Lexicon Morph-Only Canonicalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restrict lexicon canonical collapse to true morphology-backed variants and preserve standalone learner-worthy forms.

**Architecture:** Keep broad candidate discovery for operator visibility and linked-form metadata, but narrow `collapse_to_canonical` so it only fires when the candidate is supported by explicit morphology evidence such as the irregular map or suffix normalization. Semantic-only WordNet canonical-label matches should no longer collapse common headwords, and morphology-related forms with standalone meanings should remain separate or linked.

**Tech Stack:** Python 3.13, lexicon canonicalization/build-base pipeline, JSONL snapshot artifacts, pytest/unittest.

---

### Task 1: Add failing regression tests

**Files:**
- Modify: `tools/lexicon/tests/test_canonical_forms.py`

**Steps:**
1. Add a failing test proving semantic-only WordNet label matches do not collapse `almost -> about`.
2. Add a failing test proving semantic-only WordNet label matches do not collapse `total -> full`.
3. Add a failing test proving a morphology-related form with its own standalone meaning is preserved instead of collapsed.
4. Run the targeted test file and confirm the new tests fail for the current implementation.

### Task 2: Restrict collapse eligibility to morphology-backed candidates

**Files:**
- Modify: `tools/lexicon/canonical_forms.py`

**Steps:**
1. Separate morphology evidence from semantic/WordNet label evidence in candidate scoring.
2. Permit `collapse_to_canonical` only when the winning candidate has explicit morphology support.
3. Keep broad candidate discovery for `keep_both_linked`, `keep_separate`, and ambiguity reporting.
4. Preserve standalone learner-worthy forms when the surface form has its own supported meaning.

### Task 3: Verify snapshot impact and refresh docs/status

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. Run targeted canonicalization tests and the full lexicon suite.
2. Re-check the `words-1000-20260313-main-real` snapshot behavior or equivalent focused analysis to confirm bad semantic collapses are no longer considered valid under the new rule.
3. Add a concise status-board entry with verification evidence.

### Task 4: Review diff and prepare PR handoff

**Files:**
- Review only

**Steps:**
1. Inspect the final diff for accidental scope expansion.
2. Summarize the behavior change, test evidence, and remaining risks.
