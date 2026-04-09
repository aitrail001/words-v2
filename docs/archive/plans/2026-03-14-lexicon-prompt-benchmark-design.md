# Lexicon Prompt Benchmark Design

Date: 2026-03-14
Owner: Codex

## Goal

Measure the speed and quality tradeoff between:

1. `gpt-5.1-chat` and the current stronger baseline model
2. a bare word-only lexicon prompt and the current WordNet-grounded prompt

using the real lexicon JSON schema, parser, and validator.

## Problem

The repo already has model-quality notes in `tools/lexicon/MODEL_BENCHMARKS.md`, but those runs do not answer the current operational question:

- should we use `gpt-5.1-chat` for this workflow?
- how much quality do we lose if we remove the WordNet grounding context and prompt with only the word itself?

The existing enrichment pipeline only exposes the grounded per-word prompt path, so there is no reproducible way to benchmark grounded versus word-only prompts under the same validation rules.

## Chosen Approach

### 1. Add a dedicated enrichment benchmark harness

Create a small benchmark module that:

- loads a fixed benchmark set of lexeme+sense inputs
- builds prompts in one of two modes:
  - `grounded`
  - `word_only`
- runs them against a chosen model through the real OpenAI-compatible transport
- validates outputs through the existing JSON validators
- records latency, retries, and structured quality metrics

This benchmark is separate from `benchmark-selection`, because the current question is about enrichment generation rather than sense-selection or rerank quality.

### 2. Use a bounded fixed prompt set

Use a short tracked benchmark dataset, not a large production run.

The set should include:

- mixed POS
- ambiguous/polysemous common words
- at least one distinct-derived variant entry
- at least one non-general entity-category entry

This gives enough signal to compare prompt styles without spending hours or hiding the results in a massive uncontrolled batch.

### 3. Run a 2x2 live comparison matrix

Run:

- `gpt-5.1-chat` + `word_only`
- `gpt-5.1-chat` + `grounded`
- baseline model + `word_only`
- baseline model + `grounded`

The baseline model should be the current preferred production-quality choice, which today is `gpt-5.4`.

### 4. Keep all non-target variables fixed

For fair comparison:

- same transport path
- same system prompt
- same output schema
- same validator
- same benchmark items
- same execution order controls where possible

The only changing variables are:

- `model`
- `prompt_mode`

### 5. Report both quality and speed

Record:

- total batch wall time
- per-item latency
- valid-response count
- repair count
- retry count
- average confidence
- average definition length
- average usage-note length
- CEFR distribution

Also produce a short qualitative comparison for a few tracked difficult words so the final recommendation is not based only on aggregate numbers.

## Alternatives Considered

### A. Run only `gpt-5.1-chat`

This is cheaper and faster, but it cannot answer whether any quality loss comes from the model or from removing WordNet grounding.

### B. Reuse the existing selection benchmark

That benchmark answers a different question. It compares deterministic selection and rerank modes, not enrichment prompt structure.

### C. Run a large 1000-word or 5000-word live benchmark

That would be slow, expensive, and harder to review manually. A small tracked matrix is the right first decision tool.

## Success Criteria

1. There is a reproducible benchmark harness for enrichment prompt/model comparisons.
2. It supports at least `grounded` and `word_only` prompt modes.
3. It records structured speed and quality artifacts per run.
4. A live benchmark is executed for the requested matrix including `gpt-5.1-chat`.
5. The repo contains a tracked report with a recommendation based on the measured results.
