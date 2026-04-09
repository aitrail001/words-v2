# Lexicon Batched Enrichment Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a bounded batching benchmark for lexicon enrichment so we can compare `gpt-5-nano` and `gpt-5.1` using `2`, `4`, and `8` words per request across `16`, `64`, and `128` word datasets, while preserving per-word validation, streaming durability, and resume behavior.

**Architecture:** Extend the benchmark harness with a request-grouping dimension that builds batched prompts, validates and splits grouped responses back into per-word units, and records both request-level and word-level metrics. Keep the existing `word_only` baseline semantics and quality rubric so results remain directly comparable with the current single-word benchmark.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSON/JSONL benchmark artifacts, pytest/unittest, OpenAI-compatible Responses API via persistent Node worker.

---

### Task 1: Define tracked benchmark datasets for `16`, `64`, and `128` words

**Files:**
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_16.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_16.meta.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_64.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_64.meta.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_128.json`
- Create: `tools/lexicon/benchmarks/enrichment_prompt_words_128.meta.json`
- Modify: `tools/lexicon/enrichment_benchmark.py`
- Test: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Write failing tests**

Cover dataset resolution and metadata loading for the new built-in dataset names.

**Step 2: Implement the datasets**

Curate them as deterministic prefixes/extensions of the tracked benchmark set so comparison remains simple.

**Step 3: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 2: Add failing tests for batched prompt/response assembly

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write failing tests**

Cover:

- grouped word-only prompt assembly for `2`, `4`, and `8` lexemes
- grouped response schema assembly
- safe splitting of grouped responses into per-word payloads
- rejection of duplicate or missing grouped lexeme sections

**Step 2: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 3: Implement batched generation helpers

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Add grouped prompt builders**

Build a stable `word_only` grouped prompt format that clearly separates lexemes and allowed sense IDs per lexeme.

**Step 2: Add grouped schema builders**

Require a top-level grouped object that can be deterministically split back into per-word enrichment payloads.

**Step 3: Add grouped validation/splitting**

Validate the grouped response and emit per-word rows plus grouped retry/repair stats.

**Step 4: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 4: Extend the benchmark harness with request-group size support

**Files:**
- Modify: `tools/lexicon/enrichment_benchmark.py`
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Write failing tests**

Cover:

- request-group size becomes part of each benchmark case
- case summary records request count and effective seconds per word
- streaming `.rows.jsonl`, `.failures.jsonl`, and `.progress.json` remain correct under grouped requests
- rerun resume skips already completed words even when prior requests were grouped

**Step 2: Implement grouped execution**

Process lexemes in grouped requests while preserving per-word durability.

**Step 3: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 5: Expose grouped benchmarking through the CLI

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing tests**

Cover CLI argument parsing for request-group sizes and new built-in dataset names.

**Step 2: Implement CLI wiring**

Allow the benchmark command to run the grouped matrix without bespoke local scripts.

**Step 3: Run targeted tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py -q
```

### Task 6: Run focused verification for the batching feature

**Files:**
- No new files expected

**Step 1: Run the focused benchmark-related suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 7: Run the live batching matrix

**Files:**
- Benchmark artifacts under `/tmp`

**Step 1: Run the benchmark grid**

Benchmark:

- models: `gpt-5-nano`, `gpt-5.1`
- prompt mode: `word_only`
- request-group sizes: `2`, `4`, `8`
- datasets: `16`, `64`, `128`

**Step 2: Monitor and resume as needed**

Confirm grouped runs preserve per-word progress and resumability.

### Task 8: Write the batching report and refresh live status

**Files:**
- Create: `docs/plans/2026-03-16-lexicon-batched-enrichment-benchmark-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Record the result**

Document:

- throughput deltas vs the single-word baseline
- repair/failure deltas
- any grouped failure blast-radius issues
- recommended request-group size, if any
- whether batching is safe enough for the 30K enrichment path

### Task 9: Final verification before completion

**Files:**
- No new files expected

**Step 1: Re-run the lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```
