# Lexicon Prompt Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reproducible enrichment benchmark that compares `gpt-5.1-chat` and `gpt-5.4` across `word_only` versus WordNet-grounded prompt modes, then run the live matrix and report the results.

**Architecture:** Add a dedicated benchmark harness for the per-word lexicon enrichment path, create a tracked benchmark dataset, expose prompt-mode selection without changing the production default, and emit structured artifact summaries plus a short evidence-backed report.

**Tech Stack:** Python 3.13, `tools/lexicon`, existing OpenAI-compatible transport, pytest/unittest, JSON artifacts.

---

### Task 1: Add failing tests for prompt-mode support

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write a failing prompt test**

Add tests proving:

- `grounded` prompt mode includes WordNet grounding context
- `word_only` prompt mode omits the grounding block but keeps the same schema and hard constraints

**Step 2: Run the targeted test and verify it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 2: Add failing tests for the benchmark harness

**Files:**
- Create: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Write a failing harness test**

Cover:

- benchmark dataset loading
- matrix execution summary shape
- prompt-mode propagation
- latency/quality metric aggregation

**Step 2: Run the new test file and verify it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 3: Implement prompt-mode support

**Files:**
- Modify: `tools/lexicon/enrich.py`

**Step 1: Add prompt-mode selection**

Keep the current grounded prompt as the default, and add a `word_only` alternative for benchmark use.

**Step 2: Keep validation/output behavior unchanged**

Only prompt construction should vary, not schema validation or output normalization.

**Step 3: Run prompt tests and verify they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 4: Implement the benchmark harness and tracked dataset

**Files:**
- Create: `tools/lexicon/enrichment_benchmark.py`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words.json`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Add a small tracked benchmark dataset**

Include mixed POS, ambiguity, one distinct-derived variant, and one entity-category item.

**Step 2: Implement benchmark execution**

The harness should:

- build benchmark lexeme/sense inputs
- execute prompt/model runs
- validate responses
- record timing and quality metrics
- write machine-readable artifacts

**Step 3: Add a CLI entrypoint**

Expose a command for running the benchmark locally with model and prompt-mode controls.

**Step 4: Run the targeted test scope and verify it passes**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py -q
```

### Task 5: Run the full lexicon test suite

**Files:**
- No new code changes expected

**Step 1: Run the full suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

### Task 6: Execute the live benchmark matrix

**Files:**
- Create: benchmark artifact directory under `/tmp` or a dated repo-safe artifact path

**Step 1: Run the 2x2 benchmark**

Execute the live matrix for:

- `gpt-5.1-chat`
- `gpt-5.4`
- `grounded`
- `word_only`

**Step 2: Collect structured artifacts**

Keep raw outputs and a summary JSON for each run.

### Task 7: Write the report and refresh live status

**Files:**
- Create: `docs/plans/2026-03-14-lexicon-prompt-benchmark-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write the report**

Summarize:

- the exact matrix
- speed results
- quality results
- recommendation

**Step 2: Update project status**

Add a concise evidence-backed note only if the benchmark changes the recorded recommendation or live lexicon rollout plan.

### Task 8: Final verification before completion

**Files:**
- No new code changes expected

**Step 1: Re-run the verification commands used for the completion claim**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```
