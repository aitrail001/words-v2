# Lexicon Benchmark Hardening Design

Date: 2026-03-15
Owner: Codex

## Goal

Make the live lexicon enrichment path robust enough to complete the tracked `curated_100` benchmark on the real gateway, fast enough to be operationally viable for the later `30K` enrichment rollout, and structured so API-level schema enforcement reduces prompt-only JSON fragility.

## Problem

The new `benchmark-enrichment` workflow is functionally correct and fully tested at the code level, but the first real `curated_100` run exposed operational weaknesses:

1. a single lexeme can fail the whole case because of a minor schema-invalid field such as an empty string inside `antonyms`
2. the benchmark case only writes output after the full case completes, so a failure late in the run loses all prior successful lexeme work
3. the Node transport currently launches a fresh subprocess per lexeme, which adds avoidable overhead at benchmark scale and would be expensive for `30K`
4. the Node transport currently relies on prompt-only JSON discipline instead of API-level `json_schema` structured outputs
5. the prompt is not arranged for good prompt-cache reuse because dynamic lexeme content appears too early

This is acceptable for a tiny smoke benchmark, but not for a multi-hour tracked benchmark and definitely not for a `30K` production enrichment run.

## Root Cause

The observed failure was:

- model: `gpt-5.1-chat`
- prompt mode: `word_only`
- lexeme: `sound`
- error: `OpenAI-compatible enrichment payload field 'antonyms[0]' must be a non-empty string`

The error was intermittent rather than deterministic. The same lexeme later passed repeatedly in isolation. That points to a flaky model-output shape issue, not a stable semantic incompatibility in the prompt.

## Chosen Approach

### 1. Normalize trivially invalid string-list items safely

For string-list fields such as:

- `secondary_domains`
- `synonyms`
- `antonyms`
- `collocations`
- `grammar_patterns`

strip whitespace and drop empty items before failing validation.

This is intentionally narrow. It does not invent content, does not rewrite meanings, and only removes obviously invalid empty placeholders that should never survive schema validation.

### 2. Broaden retry/repair behavior for validation failures

Per-word enrichment already retries some transient failures and can issue repair prompts. This needs to be hardened so that validation failures are treated as retryable at the lexeme level rather than as immediate terminal failures after a too-small number of attempts.

The rule:

- first invalid response -> repair prompt using exact validation error
- if still invalid -> another repair or fresh retry within a bounded attempt budget
- only then mark the lexeme as failed

This keeps the pipeline strict while acknowledging flaky real-model behavior.

### 3. Add checkpoint/resume support to the benchmark harness

The benchmark harness should write progress per lexeme or at least per successfully completed lexeme batch inside each model/prompt case.

Each case should have:

- partial progress artifact
- completed rows artifact
- failure sidecar if a lexeme still fails after bounded retries

On rerun, the case should resume from completed lexemes instead of restarting from zero.

### 4. Replace per-request Node subprocess spawning with a persistent worker

The current Node path starts a new `node ...openai_compatible_responses.mjs` subprocess for every lexeme. That is simple, but it adds avoidable fixed overhead on every request.

The transport should instead keep one long-lived Node worker process alive and exchange newline-delimited JSON messages over stdin/stdout:

- Python side keeps a persistent subprocess handle
- each request gets a unique request id
- Node side executes the OpenAI call and emits one JSON response line per request

This reduces process startup churn and better matches the later `30K` run.

### 5. Move schema enforcement to the API call level in the Node path

The Node Responses API request should include a real structured-output `json_schema` payload instead of relying only on prompt text that says "return JSON only."

That means:

- build the schema once on the Python side
- pass it into the Node worker payload
- Node forwards it in the API request

Local validation still stays in place as a second-line defense, but the API call itself should be asked to enforce the shape.

### 6. Add explicit `reasoning="none"` support

The CLI and transport currently support `low|medium|high` effort, but not explicit `none`.

For latency-sensitive enrichment runs, explicit `none` should be available and benchmarked, so we are not relying on undocumented gateway defaults.

### 7. Reorder prompts for prompt-cache friendliness

The stable instructions and schema-related rules should appear first, and the dynamic lexeme/sense payload later.

This keeps:

- shared prompt prefixes longer
- prompt caching more likely to help
- dynamic variation pushed toward the tail

### 8. Treat `curated_100` as the production-hardening gate for `30K`

The `100`-word benchmark is not just a benchmark convenience. It is the first bounded proof that the enrichment path can survive the kinds of flaky real-model behavior that will otherwise make a `30K` run operationally brittle.

That means the hardening should be designed so it can later be reused directly by the real large-run enrichment path:

- per-lexeme progress persistence
- bounded retry policies by failure class
- durable failure capture
- resume-by-default execution

### 9. Extend the benchmark matrix to `gpt-5-mini` and `gpt-5-nano`

After the transport and prompt changes land, rerun bounded comparisons including:

- `gpt-5.1-chat`
- `gpt-5.1`
- `gpt-5-mini`
- `gpt-5-nano`

The goal is to compare both speed and learner-facing quality, not only latency.

### 10. Preserve benchmark semantics

The benchmark should still measure the same underlying quality/speed question:

- same models
- same prompt modes
- same validator
- same rubric logic

The hardening changes are operational only. They should not quietly lower the quality bar beyond the narrow normalization of empty string-list entries.

## Alternatives Considered

### A. Rerun until it happens to pass

Rejected. This hides the operational weakness and produces non-reproducible benchmark execution.

### B. Relax the whole validator

Rejected. That would lower data quality too broadly and make the benchmark less representative of the production path.

### C. Fix only the benchmark harness without touching validation retry

Rejected. Resume/checkpointing is necessary, but the real lexeme generation path still needs broader bounded recovery from intermittent invalid payloads.

## Success Criteria

1. The exact empty-string list-item failure class is covered by tests and no longer kills a benchmark run.
2. Validation failures trigger bounded retry/repair behavior at the lexeme level.
3. Benchmark cases persist progress and can resume instead of restarting from zero.
4. The Node transport uses a persistent worker instead of per-request subprocess spawning.
5. The Node API request uses real structured `json_schema` output enforcement.
6. Explicit `reasoning="none"` is supported end-to-end.
7. Prompt ordering is cache-friendlier without changing semantics.
8. The hardening shape is compatible with the later `30K` enrichment run rather than being benchmark-only glue.
9. The full comparison results are collected for `gpt-5.1-chat`, `gpt-5.1`, `gpt-5-mini`, and `gpt-5-nano`.
10. The final report records both the hardening change and the completed benchmark results.
