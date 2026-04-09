# Lexicon Holdout Benchmark And Rerank Modes Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit tuning and holdout benchmark datasets, expose rerank source modes (`selected_only`, `candidates`, `full_wordnet`), improve deterministic selector rules using only pattern-based heuristics, and rerun deterministic-vs-rerank comparisons on both datasets to guard against overfitting.

**Architecture:** Keep deterministic selection as the default production backbone. Add benchmark word-list data under `tools/lexicon/benchmarks/` and a thin benchmark runner/CLI that can build a deterministic baseline snapshot, run grounded rerank under a chosen source mode, compare outputs, and emit auditable artifacts. Extend rerank so it can choose from: the already-selected deterministic senses only, a bounded ranked candidate shortlist, or a broader full-WordNet candidate pool. Use the benchmark outputs plus the learner-priority rubric to decide whether deterministic heuristics improved generally or merely memorized the tuning set.

**Tech Stack:** Python stdlib, existing lexicon CLI/build-base/rerank/compare modules, Node OpenAI-compatible transport, `unittest`, JSON/JSONL artifacts in `/tmp` and snapshot directories.

---

### Task 1: Add benchmark datasets and runner shape

**Files:**
- Create: `tools/lexicon/benchmarks/tuning_words.json`
- Create: `tools/lexicon/benchmarks/holdout_words.json`
- Create/Modify: `tools/lexicon/benchmark_selection.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Create/Modify: `tools/lexicon/tests/test_benchmark_selection.py`

**Step 1: Write failing tests**
- add tests for loading benchmark word lists
- add CLI tests for a benchmark command or equivalent runner entrypoint
- add tests for benchmark artifact summary shape

**Step 2: Verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_cli tools.lexicon.tests.test_benchmark_selection`
Expected: fail before implementation.

**Step 3: Implement minimal benchmark flow**
- load tuning/holdout words from benchmark files
- write deterministic snapshot output under a run directory
- optionally run rerank for a chosen mode
- write compare summary JSON for each dataset

### Task 2: Add rerank source modes

**Files:**
- Modify: `tools/lexicon/rerank.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_rerank.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Write failing tests**
- add tests for `selected_only`, `candidates`, and `full_wordnet` source modes
- ensure each mode constrains the LLM to the provided candidate IDs only
- ensure CLI passes the mode through correctly

**Step 2: Verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_rerank tools.lexicon.tests.test_cli`
Expected: fail before implementation.

**Step 3: Implement the modes**
- `selected_only`: use the deterministic snapshot senses only
- `candidates`: use a bounded ranked candidate shortlist (existing behavior generalized)
- `full_wordnet`: use the full available WordNet candidate pool for the lemma, still grounded and validated
- keep hard validation that the LLM may only return provided `wn_synset_id`s

### Task 3: Improve deterministic selector using only pattern-based rules

**Files:**
- Modify: `tools/lexicon/wordnet_utils.py`
- Modify: `tools/lexicon/wordnet_provider.py` only if metadata is needed
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/SELECTION_RUBRIC.md`

**Step 1: Write failing regression tests**
- add or refine tests that capture generic failure classes (alias-like label drift, complaint/penalty/attack tails, abstract/legal/geographic noun overreach)
- include a couple of non-tuning holdout-style tests to reduce overfitting risk

**Step 2: Verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base`
Expected: fail before heuristic changes.

**Step 3: Implement minimal pattern-based changes**
- adjust only generic scoring and selection rules
- no lemma-specific hardcoding
- keep deterministic output and WordNet grounding

### Task 4: Run tuning + holdout comparisons and record evidence

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Run full verification**
Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: pass

Run: `PYTHONPYCACHEPREFIX=/tmp/lexicon-holdout-pycache python3 -m py_compile tools/lexicon/wordnet_utils.py tools/lexicon/cli.py tools/lexicon/rerank.py tools/lexicon/compare_selection.py tools/lexicon/benchmark_selection.py`
Expected: pass

**Step 2: Run benchmark artifacts**
- build tuning baseline and compare deterministic vs rerank under at least one grounded mode
- build holdout baseline and compare deterministic vs rerank under the same mode
- if time allows, run all three rerank source modes on a small sample to compare behavior

**Step 3: Record conclusions honestly**
- capture whether the selector improved on both tuning and holdout
- note whether `selected_only`, `candidates`, or `full_wordnet` gives the most useful rerank behavior
