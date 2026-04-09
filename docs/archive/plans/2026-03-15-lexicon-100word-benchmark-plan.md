# Lexicon 100-Word Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a tracked 100-word lexicon enrichment benchmark with explicit category coverage and a rubric-based quality summary across `gpt-5.1-chat`, `gpt-5.1`, and `gpt-5.4`, each under `word_only` and `grounded` prompt modes.

**Architecture:** Reuse the new enrichment benchmark harness, add a fixed 100-word dataset plus category metadata, generate a structured rubric-oriented review summary from the produced rows, and report the quality/speed tradeoffs using one stable benchmark set committed to the repo.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSON benchmark datasets, existing Node OpenAI-compatible transport, pytest.

---

### Task 1: Add the tracked 100-word benchmark dataset and metadata

**Files:**
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_100.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_100.meta.json`
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Build the final fixed list**

Compose the 100-word set from:

- existing tracked benchmark buckets
- the current small-set words
- curated supplements for distinct variants, entities, and harder learner-relevant tail words

**Step 2: Add category metadata**

Store each word’s benchmark class so later reporting can break down speed/quality by type.

**Step 3: Add failing tests**

Assert:

- the dataset has exactly 100 unique words
- required categories are represented
- the metadata and the word list stay aligned

**Step 4: Run the dataset test and verify it fails first**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 2: Extend the benchmark harness for dataset metadata and rubric summaries

**Files:**
- Modify: `tools/lexicon/enrichment_benchmark.py`
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Load metadata alongside words**

Expose category labels in the benchmark payload.

**Step 2: Add rubric-style summary helpers**

Compute structured summary counters such as:

- variant-linked note present
- entity-aware note present
- suspicious verb-form generation
- full selected-row completion vs dropped rows

Keep the rubric lightweight and deterministic so it can run over all models and prompt modes.

**Step 3: Run tests and verify they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 3: Refresh CLI/reporting support if needed

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Ensure the benchmark command can target the new 100-word dataset**

This may require no code change if dataset-path support is already enough; if so, only tests/docs need touch-up.

**Step 2: Run the targeted CLI scope**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 4: Run the full lexicon suite

**Files:**
- No code changes expected

**Step 1: Run the full suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

### Task 5: Execute the 100-word live benchmark matrix

**Files:**
- Benchmark artifacts under `/tmp`

**Step 1: Run the matrix**

Run:

- `gpt-5.1-chat`
- `gpt-5.1`
- `gpt-5.4`
- `word_only`
- `grounded`

against the fixed 100-word set.

**Step 2: If the full 100-word run is too expensive/slow for one model**

Record that with exact timing evidence and fall back to a bounded tracked subset only if needed, documenting the reason clearly.

### Task 6: Write the expanded report

**Files:**
- Modify: `docs/plans/2026-03-15-lexicon-prompt-benchmark-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Expand the report**

Add:

- 100-word dataset composition
- category-level breakdowns
- rubric summary results
- final recommendation

### Task 7: Final verification before completion

**Files:**
- No code changes expected

**Step 1: Re-run the full lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```
