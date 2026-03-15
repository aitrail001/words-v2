## Lexicon Batched Enrichment Benchmark Report

Date: 2026-03-16
Owner: Codex

## Goal

Test whether sending multiple lexemes in one LLM request improves lexicon enrichment throughput enough to justify using grouped requests for the later 30K rollout.

This report closes the batching experiment. The recommendation is to discard grouped enrichment as a rollout path and keep one-word-per-request enrichment as the production method.

## Scope

This benchmark covered:

- models: `gpt-5-nano`, `gpt-5.1`
- prompt mode: `word_only`
- request group sizes: `2`, `4`, `8`
- live dataset: `curated_16`
- transport: persistent Node worker
- structured outputs: strict API-level schema enforcement

Planned larger runs on `curated_64` and `curated_128` were intentionally not started after the `curated_16` live evidence showed that grouped requests were already too fragile to justify further rollout work.

## Environment Notes

The first live attempt from the fresh worktree failed before any meaningful model comparison because the Node worker dependency tree was missing in that worktree. The immediate symptom was:

- `Cannot find package 'openai' imported from tools/lexicon/node/openai_compatible_responses.mjs`

That was an environment issue, not a model result. It was fixed locally with `npm --prefix tools/lexicon/node ci`, after which the benchmark was resumed.

Because the same output directory was reused, some artifact files still contain early pre-fix failure rows. Only the post-fix completed case summaries below should be used for conclusions.

## Finished Results

### Post-fix completed grouped cases

| Model | Group size | Lexemes | Valid rows | Failed lexemes | Repairs | Retries | Batch seconds | Effective seconds / word | Outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `gpt-5-nano` | `2` | `16` | `84` | `0` | `1` | `3` | `617.580` | `38.599` | Completed, much slower than the recommended single-word path |
| `gpt-5-nano` | `4` | `16` | `22` | `8` | `0` | `3` | `1020.380` | `63.774` | Partial failure, unacceptable |
| `gpt-5-nano` | `8` | `16` | `0` | `16` | `0` | `0` | `768.729` | `48.046` | Total failure |
| `gpt-5.1` | `2` | `16` | `84` | `0` | `0` | `0` | `361.628` | `22.602` | Completed on this small set, but only marginally persuasive |
| `gpt-5.1` | `4` | `16` | `28` | `8` | `0` | `3` | `1036.469` | `64.779` | Partial failure, unacceptable |

### Invalid or non-comparable case artifacts

- `gpt-5.1` with group size `8` was left with an old pre-fix checkpoint artifact dominated by the missing-package failure and was not rerun after the environment fix.
- Since `gpt-5-nano g8` already failed completely and both `g4` runs failed badly, rerunning `gpt-5.1 g8` was not worth further time or API spend.

## Failure Modes

The key failure mode after the environment fix was not JSON-schema rejection. It was grouped-request timeout behavior.

Observed post-fix grouped failures were dominated by:

- `Node OpenAI-compatible transport timed out after 60 seconds`

This matters more than the raw mean latency because grouped requests enlarge the blast radius:

- with one-word requests, a timeout loses one lexeme
- with four-word requests, one timeout can lose four lexemes at once
- with eight-word requests, one timeout can wipe out a whole batch

That blast-radius effect is exactly what happened in `g4` and `g8`.

## Comparison To The Current Recommended Path

The currently recommended production path already has a completed live benchmark on `curated_100`:

- `gpt-5-nano word_only`: `399` valid rows, `0` failed lexemes, `4` repairs, `21.965s` average latency
- `gpt-5.1 word_only`: `398` valid rows, `0` failed lexemes, `3` repairs, `23.816s` average latency

Those single-word results come from a different dataset size, so they are not a perfect apples-to-apples control for `curated_16`. Even with that limitation, the grouped evidence is still decisive:

- `gpt-5-nano g2` was clearly worse than the single-word recommendation
- `g4` was bad for both tested models
- `g8` was unusable
- the only non-failing grouped case with plausible speed, `gpt-5.1 g2`, was measured on a tiny sample and did not justify the extra code path, higher timeout exposure, and larger failure blast radius

## Decision

Discard multi-word enrichment requests as a 30K rollout method.

Operational recommendation:

- keep one-word-per-request enrichment as the only rollout path
- keep `gpt-5-nano word_only` as the default 30K model
- keep `gpt-5.1 word_only` as the fallback
- do not continue the grouped benchmark to `curated_64` or `curated_128`
- do not merge batching-specific benchmark code into the mainline implementation

## Why The Method Is Rejected

Grouped requests failed on the actual things that matter for a 30K run:

- they did not show a robust throughput win
- they raised timeout risk sharply as group size increased
- they increased failure blast radius from one lexeme to many lexemes
- they would complicate resume, debugging, and operator monitoring for little or no demonstrated rollout value

For a 30K enrichment run, durability and recoverability matter more than a small best-case latency improvement on a 16-word sample. The single-word pipeline already provides incremental flush-to-disk outputs, checkpointed resume, and contained failure handling. Grouped requests weaken those operational properties instead of improving them.
