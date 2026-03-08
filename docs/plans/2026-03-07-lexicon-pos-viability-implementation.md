# Lexicon POS Viability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve learner-facing adjective/adverb surfacing for mixed-POS English lemmas without hard POS quotas, while keeping noun/verb-only lemmas like `break` unchanged.

**Architecture:** Keep the existing per-sense ranking in `tools/lexicon/wordnet_utils.py`, then add a second lightweight POS-viability layer driven by exact-form WordNet `lemma_count` aggregates and near-cutoff score checks. The selector should only expand coverage when a high-evidence adjective/adverb candidate would otherwise be squeezed out and the operator ceiling allows it.

**Tech Stack:** Python stdlib, existing lexicon build pipeline, `unittest`, local WordNet data.

---

### Task 1: Add failing mixed-POS coverage tests

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`

**Step 1: Write failing tests**
- add a test that a strong adjective candidate for `right` can surface without removing all noun/verb coverage
- add a test that a strong adjective candidate for `open` or `close` can surface when exact-form counts justify it
- add a test that `break` remains noun/verb-only even when the selector expands broad words
- add a test that the selector can expand within the ceiling when a newly viable adjective/adverb meaning would otherwise be dropped

**Step 2: Run targeted tests to verify failure**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base.BuildBaseTests.test_build_base_records_surfaces_high_value_adjectives_for_mixed_pos_words tools.lexicon.tests.test_build_base.BuildBaseTests.test_build_base_records_keeps_break_noun_verb_only`
Expected: one or more tests fail before implementation.

### Task 2: Implement POS viability and adaptive expansion

**Files:**
- Modify: `tools/lexicon/wordnet_utils.py`
- Modify: `tools/lexicon/build_base.py` only if selector inputs need threading (likely no behavioral change)

**Step 1: Add POS evidence helpers**
- compute exact-form `lemma_count` aggregates by POS for a lemma’s candidate senses
- derive soft viability flags for adjective/adverb POS only when evidence is meaningfully competitive

**Step 2: Add near-cutoff coverage logic**
- allow a viable adjective/adverb candidate to receive a diversity-style boost only when its raw score is close enough to the current cutoff
- avoid hard guarantees or mandatory POS reservations

**Step 3: Expand selected count only when needed**
- within the operator-provided `--max-senses` ceiling, allow the selector to expand if a viable uncovered POS would otherwise be excluded from the chosen set
- keep the default shape conservative; broad words should not all expand automatically

**Step 4: Keep deterministic behavior**
- no lemma-specific allowlists
- no model calls or external corpora beyond existing WordNet inputs

### Task 3: Verify broad behavior and update docs/status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `docs/status/project-status.md`

**Step 1: Run full test and compile verification**
Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: pass

Run: `PYTHONPYCACHEPREFIX=/tmp/lexicon-ranking-pycache python3 -m py_compile tools/lexicon/wordnet_utils.py tools/lexicon/wordnet_provider.py tools/lexicon/build_base.py tools/lexicon/cli.py`
Expected: pass

**Step 2: Run broader sample validation**
Run the 50-word `build-base --max-senses 8` sweep and inspect mixed-POS words such as `right`, `clear`, `open`, `close`, `direct`, `sound`, `present`, and `light`.
Expected: some additional learner-relevant adjective/adverb coverage appears, while `break` remains noun/verb-only.

**Step 3: Record status evidence**
- update operator-facing docs with the new soft POS-viability behavior
- update `docs/status/project-status.md` with fresh evidence from tests and the broader sample
