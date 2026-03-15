# Lexicon Benchmark Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden and speed up the enrichment and benchmark execution path so the real `curated_100` benchmark completes reliably on the gateway, the same execution model is safe to reuse for the later `30K` enrichment rollout, and the transport/prompt path is benchmarked across `gpt-5.1-chat`, `gpt-5.1`, `gpt-5-mini`, and `gpt-5-nano`.

**Architecture:** Keep prompt semantics and benchmark scoring aligned, but add narrow payload normalization for empty string-list entries, broaden bounded retry/repair behavior for validation failures, make benchmark cases checkpoint/resume per lexeme, replace per-request Node subprocess spawning with a persistent worker, enforce structured `json_schema` output at the API level in the Node path, add explicit `reasoning="none"` support, and reorder prompts so stable instructions precede dynamic lexeme content for better prompt-cache behavior.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSON artifacts, pytest/unittest, existing Node OpenAI-compatible transport.

---

### Task 1: Add failing tests for safe list-item normalization

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write failing tests**

Cover the exact observed bug class:

- empty string items inside `antonyms`
- whitespace-only items inside other string-list fields
- mixed valid and empty items preserve valid content and drop only invalid blanks

**Step 2: Run the targeted test and verify it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 2: Add failing tests for bounded validation retry behavior

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write failing tests**

Cover:

- invalid payload on first attempt followed by valid payload on retry succeeds
- repair/retry stats reflect the recovery path
- repeated invalid payloads still fail after the bounded attempt budget

**Step 2: Run the targeted test and verify it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 3: Add failing tests for benchmark checkpoint/resume behavior

**Files:**
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`
- Modify: `tools/lexicon/enrichment_benchmark.py`

**Step 1: Write failing tests**

Cover:

- case progress persists after completed lexemes
- rerun resumes and skips already completed lexemes
- case summary still reflects the final completed rows
- failure sidecar or checkpoint artifact is written when a lexeme fails

**Step 2: Run the benchmark test file and verify it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 4: Add failing tests for persistent Node worker and structured schema transport

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/node/openai_compatible_responses.mjs`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Write failing tests**

Cover:

- persistent Node worker handles multiple requests without respawning
- Node request payload includes API-level structured `json_schema`
- explicit `reasoning="none"` is forwarded
- prompt text no longer carries the entire schema dump as the only enforcement mechanism

**Step 2: Run the targeted tests and verify they fail**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 5: Implement the transport and prompt hardening

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/node/openai_compatible_responses.mjs`

**Step 1: Add a persistent Node worker**

Keep one subprocess alive and exchange JSON request/response messages instead of starting one Node process per lexeme.

**Step 2: Add structured `json_schema` output support**

Pass the real schema into the Node Responses API request.

**Step 3: Add explicit `reasoning="none"` support**

Allow it in the Python and CLI path.

**Step 4: Reorder prompts for shared-prefix stability**

Move stable instructions ahead of dynamic word/sense payload while preserving semantics.

**Step 5: Run the targeted enrichment tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 6: Implement benchmark-side streaming and resume hardening

**Files:**
- Modify: `tools/lexicon/enrich.py`

**Step 1: Add narrow string-list normalization**

Drop only blank/whitespace-only items from the known string-list fields before the payload is rejected.

**Step 2: Broaden bounded validation retry**

Treat validation failures as repairable/retryable within a bounded attempt budget and preserve stats for retries/repairs.

**Step 3: Run the targeted enrichment tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

**Files:**
- Modify: `tools/lexicon/enrichment_benchmark.py`
- Modify: `tools/lexicon/tests/test_enrichment_benchmark.py`

**Step 1: Keep per-case checkpoint artifacts**

Persist enough data to resume a partially completed case.

**Step 2: Keep rerun resume behavior**

Skip already completed lexemes on rerun and continue building the case output.

**Step 3: Keep streaming row/failure artifacts**

Expose and use durable `.rows.jsonl` and `.failures.jsonl` artifacts while the case is still running.

**Step 4: Run the targeted benchmark tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 7: Run the broader benchmark-related verification scope

**Files:**
- Modify only if a test reveals a missing dependency in benchmark CLI wiring

**Step 1: Run the related lexicon scope**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_enrichment_benchmark.py -q
```

### Task 8: Run the full lexicon suite

**Files:**
- No code changes expected

**Step 1: Run the full suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

### Task 9: Run comparison benchmarks to completion

**Files:**
- Benchmark artifacts under `/tmp`

**Step 1: Start the hardened live benchmark**

Run the matrix against `curated_100` for:

- `gpt-5.1-chat`
- `gpt-5.1`
- `gpt-5-mini`
- `gpt-5-nano`

and keep the old `gpt-5.4` only if needed for comparison continuity.

**Step 2: Monitor until completion**

If a lexeme still fails after bounded retries, confirm checkpoint artifacts preserve earlier work and rerun from the checkpoint.

### Task 10: Capture `30K` rollout implications in the report

**Files:**
- Modify: `docs/plans/2026-03-15-lexicon-prompt-benchmark-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Record the hardening**

Document:

- the failure class
- the hardening changes
- completed `curated_100` results
- speed impact of the persistent worker / structured schema / prompt changes
- speed and quality comparison for `gpt-5.1-chat`, `gpt-5.1`, `gpt-5-mini`, and `gpt-5-nano`
- why the resulting checkpoint/retry behavior matters for the later `30K` enrichment run
- updated operational recommendation if it changes

### Task 11: Refresh report and live status

**Files:**
- Modify: `docs/plans/2026-03-15-lexicon-prompt-benchmark-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Record the hardening**

Document:

- concise live status evidence only if capability state changes

### Task 12: Final verification before completion

**Files:**
- No new code changes expected

**Step 1: Re-run the full lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```
