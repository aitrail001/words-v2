# Lexicon Sense Ranking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic learner-oriented sense ranking with adaptive `4/6/8` sense selection so polysemous words like `run` and `set` include core verb and noun meanings.

**Architecture:** The ranking logic stays inside `tools/lexicon/wordnet_utils.py` so `build_base_records()` can continue to consume normalized candidate senses through a single selection helper. Tests expand in `tools/lexicon/tests/test_build_base.py` to verify verb-first ranking, noun retention, specialized-sense suppression, and adaptive cap expansion.

**Tech Stack:** Python stdlib, existing lexicon build pipeline, `unittest`.

---

### Task 1: Add failing selection tests

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`

**Step 1: Write the failing tests**
- add a test that mixed `run` verb+noun candidates include a verb in the selected top senses
- add a test that noun coverage is retained when noun senses also exist
- add a test that adaptive cap expands only when enough senses clear strong-score thresholds
- add a test that specialized noun senses lose to general verb senses in a bounded top-4 set

**Step 2: Run test to verify it fails**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base`
Expected: one or more new tests fail under the current slice-first selection logic

### Task 2: Implement ranking and adaptive cap

**Files:**
- Modify: `tools/lexicon/wordnet_utils.py`

**Step 1: Implement minimal scoring helpers**
- add POS weights
- add gloss keyword boosts/penalties
- add a weak original-order tie-break signal

**Step 2: Implement adaptive cap + guardrails**
- add logic to compute an effective selection cap within the operator-provided ceiling
- replace the hard noun guardrail with competitive noun scoring plus a derived-form noun penalty
- cap specialized senses in the first four selections

**Step 3: Keep implementation deterministic and small**
- no external corpora or model calls
- no lemma-specific hardcoding in v1

**Step 4: Run targeted tests**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base`
Expected: pass

### Task 3: Verify full lexicon suite and record docs/status

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/README.md` (if a short operator note is needed)

**Step 1: Add concise status evidence entry**
- record the new learner-oriented ranking/adaptive cap slice and verification evidence

**Step 2: Run broader verification**
Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: pass

Run: `PYTHONPYCACHEPREFIX=/tmp/lexicon-ranking-pycache python3 -m py_compile tools/lexicon/wordnet_utils.py tools/lexicon/build_base.py`
Expected: pass
