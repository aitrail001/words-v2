# Lexicon Batched Enrichment Benchmark Design

Date: 2026-03-16
Owner: Codex

## Goal

Evaluate whether small multi-word enrichment requests can improve end-to-end throughput for the lexicon enrichment pipeline without materially degrading output quality, repair rate, or failure recovery behavior.

## Context

The completed fixed-schema `curated_100` benchmark established the current single-word baseline:

- `gpt-5-nano word_only` is the fastest and strongest operational default
- `gpt-5.1 word_only` is the conservative fallback
- `grounded` underperforms `word_only` operationally on this gateway
- the transport and schema hardening work is now good enough that the next likely performance win is reducing request count rather than further polishing single-word request overhead

The current per-word shape is also small enough to make batching plausible:

- prompt: roughly `300` tokens per word in `word_only`
- output: roughly `2.7K` tokens per word on average, with a tail near `4.7K`
- official output-window limits are large enough for `gpt-5.1`, `gpt-5-mini`, and `gpt-5-nano`, but `gpt-5.1-chat` has a smaller output cap and is therefore a worse batching target

Because `gpt-5-nano` and `gpt-5.1` are the only two configurations worth carrying forward for production consideration, the batching benchmark should focus on them only.

## Problem

A pure one-word-per-request model is operationally simple and durable, but it may leave throughput on the table if fixed per-request overhead remains a meaningful part of total latency. At the same time, naive batching creates new risks:

1. one malformed response can affect multiple words at once
2. validation and repair logic become more complex because the model must keep multiple lexeme sections separated
3. disk durability must stay per-word even if generation happens per batch
4. a benchmark result that only measures request latency can miss silent quality regressions

So the experiment must preserve the current quality bar and resumability model while changing only the request grouping shape.

## Chosen Approach

### 1. Benchmark batching only in `word_only` mode

The previous benchmark already showed that `grounded` is slower and more repair-heavy. The batching question should therefore isolate one dimension:

- keep prompt mode fixed at `word_only`
- vary only the number of words per request

This prevents a larger matrix from obscuring whether batching itself helps.

### 2. Benchmark only `gpt-5-nano` and `gpt-5.1`

These are the only models that remain production candidates after the fixed-schema matrix. Excluding `gpt-5.1-chat` and `gpt-5-mini` keeps the experiment focused and reduces cost/time.

### 3. Test request-group sizes `2`, `4`, and `8`

These three sizes cover the useful range:

- `2`: low-risk batching, likely easiest for quality parity
- `4`: likely practical sweet spot if batching helps
- `8`: deliberate stress case to test whether latency/throughput gains are offset by quality or repair costs

Larger groups are not needed until one of these three demonstrates a clear win.

### 4. Test dataset sizes `16`, `64`, and `128`

These sizes provide three operational views:

- `16`: quick sanity and shape check
- `64`: medium run where repair/failure behavior becomes visible
- `128`: larger run that better reflects the production stability profile

The benchmark datasets should be tracked and deterministic so reruns stay comparable.

### 5. Keep per-word durability even when requests are batched

The implementation should continue to:

- validate response rows per word
- write successful rows to disk incrementally
- record failed words individually
- expose progress and failure artifacts while the run is still active

The request may contain multiple words, but the durable unit of progress must remain the single lexeme. This preserves resumability and keeps the 30K enrichment path operationally safe.

### 6. Add request-level metrics without replacing word-level metrics

The benchmark summary should record:

- request-group size
- request count
- request-level average latency
- effective seconds per word
- valid rows
- failed lexemes
- repairs
- retries
- schema fallback count
- partial-batch salvage behavior where relevant

The existing quality rubric should still score the final accepted rows so the batching result can be compared directly with the current single-word baseline.

### 7. Prefer bounded salvage over all-or-nothing batch failure

If a batched response is invalid in a way that can be localized to one or more words, the harness should salvage the valid words instead of discarding the whole request. If the response shape cannot be safely split or attributed, the request should fail loudly and mark all affected words as pending or failed in a way that is resumable and explicit.

This keeps the experiment useful for production decisions: if batching only works when the failure blast radius is unacceptable, that is itself a negative result.

## Alternatives Considered

### A. Add batching directly to the production 30K command first

Rejected. That would combine performance experimentation with production rollout risk.

### B. Benchmark larger groups such as `16` or `32` words immediately

Rejected. The expected output size is technically feasible on some models, but quality separation and failure blast radius would make interpretation noisy too early.

### C. Measure only latency

Rejected. The pipeline is quality-sensitive, and speed gains are not useful if repairs or dropped rows climb materially.

## Success Criteria

1. The benchmark can generate and validate grouped requests while still flushing accepted rows per word.
2. The summary reports both request-level and effective per-word metrics.
3. Runs remain resumable after partial progress or terminal failures.
4. The experiment produces a clean comparison grid for:
   - models: `gpt-5-nano`, `gpt-5.1`
   - request-group sizes: `2`, `4`, `8`
   - dataset sizes: `16`, `64`, `128`
5. The final report can answer whether batching is worth carrying into the 30K enrichment path, and if so at what group size.
