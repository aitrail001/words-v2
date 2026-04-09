# Lexicon Prompt Benchmark Report

Date: 2026-03-16
Owner: Codex

## Goal

Compare live speed, completion stability, and learner-facing output quality for the lexicon per-word enrichment path across:

- `gpt-5.1-chat`
- `gpt-5.1`
- `gpt-5-mini`
- `gpt-5-nano`

and across two prompt modes:

- `word_only`
- `grounded`

This report supersedes the earlier partial benchmark notes from the same branch. The earlier small-set results were collected before the structured-output schema was hardened to the gateway's strict `text.format.schema` requirements. The final recommendation below is based on the completed fixed-schema `curated_100` matrix.

## Scope

This benchmark compares:

- a bare word prompt with only allowed `sense_id` anchors (`word_only`), versus
- the production-style grounded prompt with selected WordNet sense context (`grounded`)

It does not compare against a full WordNet candidate-pool prompt. The grounded mode here is the current selected-sense enrichment prompt from `tools/lexicon/enrich.py`.

## Final Setup

- Transport: `openai_compatible_node`
- Node path: persistent worker process, not one subprocess per lexeme
- Request mode: schema-first structured outputs with gateway fallback when needed
- Reasoning effort: `none`
- Dataset: `curated_100`
- Output dir: `/tmp/lexicon-prompt-benchmark-20260315-curated100-schemafixed`
- Shared validator: `_validate_openai_compatible_word_payload()`

### Structured Output Hardening

The upstream gateway enforced the same strict structured-output subset documented by OpenAI:

- every object must use `additionalProperties: false`
- every key listed in `properties` must also appear in `required`
- optionality must be represented with `null`, not by omitting keys
- open-ended nested objects such as free-form `additionalProperties` maps are not acceptable in strict schemas

The final fixed schema therefore:

- uses `anyOf` for nullable fields
- makes all declared per-sense keys required
- uses a closed explicit `verb_forms` object schema

After this hardening, raw schema-enforced probes against the real endpoint no longer failed with `invalid_json_schema`, and the full benchmark matrix completed.

### Tracked 100-word Benchmark Set

The repo carries a fixed `curated_100` dataset for repeatable benchmark work:

- word list: `tools/lexicon/benchmarks/enrichment_prompt_words_100.json`
- metadata: `tools/lexicon/benchmarks/enrichment_prompt_words_100.meta.json`
- rubric support: `tools/lexicon/enrichment_benchmark.py`

Category mix:

- `common_polysemous`: `25`
- `noun_verb_crossover`: `20`
- `adj_adv_ambiguity`: `15`
- `distinct_variant`: `15`
- `entity`: `10`
- `harder_tail`: `15`

Each run records:

- `dropped_row_count`
- `distinct_variant_rows`
- `distinct_variant_linked_note_hits`
- `entity_rows`
- `entity_specific_note_hits`
- `suspicious_generated_forms`

## Final Matrix

| Model | Prompt mode | Valid rows | Failed lexemes | Repairs | Avg / lexeme (s) | Batch (s) | Avg confidence |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5.1-chat` | `word_only` | `397` | `0` | `5` | `22.890` | `2290.104` | `0.931` |
| `gpt-5.1-chat` | `grounded` | `376` | `1` | `30` | `32.165` | `3352.663` | `0.922` |
| `gpt-5.1` | `word_only` | `398` | `0` | `3` | `23.816` | `2382.779` | `0.931` |
| `gpt-5.1` | `grounded` | `375` | `2` | `44` | `35.615` | `3822.496` | `0.920` |
| `gpt-5-mini` | `word_only` | `397` | `0` | `7` | `24.499` | `2451.011` | `0.932` |
| `gpt-5-mini` | `grounded` | `385` | `0` | `32` | `29.810` | `2982.069` | `0.919` |
| `gpt-5-nano` | `word_only` | `399` | `0` | `4` | `21.965` | `2197.699` | `0.928` |
| `gpt-5-nano` | `grounded` | `389` | `0` | `28` | `29.416` | `2942.746` | `0.920` |

### Rubric Summary

| Model | Prompt mode | Dropped rows | Distinct variant rows | Variant link hits | Entity rows | Entity-specific note hits | Suspicious forms |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5.1-chat` | `word_only` | `5` | `59` | `45` | `10` | `8` | `0` |
| `gpt-5.1-chat` | `grounded` | `26` | `46` | `31` | `10` | `9` | `1` |
| `gpt-5.1` | `word_only` | `4` | `60` | `38` | `10` | `9` | `0` |
| `gpt-5.1` | `grounded` | `27` | `44` | `34` | `10` | `9` | `0` |
| `gpt-5-mini` | `word_only` | `5` | `59` | `46` | `10` | `7` | `0` |
| `gpt-5-mini` | `grounded` | `17` | `45` | `28` | `10` | `8` | `0` |
| `gpt-5-nano` | `word_only` | `3` | `60` | `40` | `10` | `7` | `0` |
| `gpt-5-nano` | `grounded` | `13` | `49` | `34` | `10` | `7` | `0` |

## Key Findings

### 1. Schema hardening was the real unlock

Before the strict schema fix, the benchmark was dominated by:

- upstream `invalid_json_schema` rejections
- gateway `502` failures on malformed strict schemas
- fallback-mode degradation that made results hard to interpret

After aligning the schema with the documented structured-output subset, the matrix completed end-to-end. This confirms the old failures were primarily schema-contract problems, not an inherent limitation of the models.

### 2. `word_only` beat `grounded` operationally across the board

Across all four models, `word_only` was:

- faster
- much less repair-heavy
- equal or better on failed-lexeme count
- equal or better on dropped-row count

Grounded mode remained usable, but it never won on the overall speed/stability tradeoff in this matrix.

### 3. `gpt-5-nano word_only` was the strongest operational default

`gpt-5-nano word_only` delivered:

- the fastest average latency: `21.965s` per lexeme
- the highest valid-row total: `399`
- zero failed lexemes
- only `4` repairs

That makes it the best pure throughput candidate for the eventual 30K run.

### 4. `gpt-5.1 word_only` is the best conservative fallback

`gpt-5.1 word_only` delivered:

- `398` valid rows
- zero failed lexemes
- only `3` repairs

It is slower than `nano`, but still highly stable and slightly stronger than `gpt-5.1-chat` on dropped rows and repair count.

### 5. Grounded mode remained semantically attractive in theory but not enough in practice

The grounded runs still preserved entity coverage and variant handling, but they paid for it with:

- far higher repair counts
- slower per-lexeme latency
- a small but real failure tail for `gpt-5.1-chat` and `gpt-5.1`

Observed grounded failures:

- `gpt-5.1-chat grounded`: failed lexeme `right`
- `gpt-5.1 grounded`: failed lexemes `case`, `fine`

Those were not infrastructure failures. They were output-selection failures such as duplicate `sense_id` returns.

## Model-by-Model Analysis

### `gpt-5.1-chat`

`word_only` is strong and production-viable:

- `397` valid rows
- zero failed lexemes
- `5` repairs
- `22.890s` per lexeme

`grounded` is clearly weaker operationally:

- `376` valid rows
- one failed lexeme
- `30` repairs
- `32.165s` per lexeme

Conclusion: if using `gpt-5.1-chat`, use `word_only`.

### `gpt-5.1`

`word_only` is strong and slightly more conservative than `gpt-5.1-chat`:

- `398` valid rows
- zero failed lexemes
- `3` repairs
- `23.816s` per lexeme

`grounded` is the weakest finished case in the matrix:

- `375` valid rows
- two failed lexemes
- `44` repairs
- `35.615s` per lexeme

Conclusion: if using `gpt-5.1`, use `word_only`.

### `gpt-5-mini`

`word_only` completed cleanly:

- `397` valid rows
- zero failed lexemes
- `7` repairs
- `24.499s` per lexeme

`grounded` also completed cleanly, but at much higher repair cost:

- `385` valid rows
- zero failed lexemes
- `32` repairs
- `29.810s` per lexeme

Conclusion: usable, but not the best winner in either speed or repair burden.

### `gpt-5-nano`

`word_only` was the operational winner:

- `399` valid rows
- zero failed lexemes
- `4` repairs
- `21.965s` per lexeme

`grounded` also completed cleanly:

- `389` valid rows
- zero failed lexemes
- `28` repairs
- `29.416s` per lexeme

Conclusion: best throughput candidate for 30K, but still prefer `word_only`.

## Recommendation

### Best default for the 30K enrichment run

Use `gpt-5-nano` with `word_only`.

Reason:

- fastest completed configuration
- zero failed lexemes
- best valid-row total
- low repair burden

### Best conservative fallback

Use `gpt-5.1` with `word_only`.

Reason:

- zero failed lexemes
- lowest repair count among the large non-nano models
- near-top valid-row total

### Do not use grounded mode as the rollout default

Reason:

- consistently slower
- consistently more repair-heavy
- slightly lower row retention
- real failure tail on `gpt-5.1-chat` and `gpt-5.1`

Grounded mode may still be worth revisiting for narrow follow-up quality slices, but it is not the best operational default for the 30K run on this gateway.

## 30K Rollout Implications

The current benchmark outcome suggests the 30K run should be launched with:

- persistent Node transport
- the fixed strict schema
- schema-first requests
- fallback behavior retained as a safety valve
- `word_only` prompt mode
- `gpt-5-nano` as the primary model

The benchmark harness changes also proved the right operational shape for 30K:

- incremental `.rows.jsonl` writes
- `.progress.json` checkpoints
- `.failures.jsonl` sidecars
- continue-after-terminal-failure case handling instead of aborting the whole run

That means the remaining risk is no longer "will the infrastructure survive the run?" It is now mostly "which model/prompt combination gives the best cost-quality tradeoff?" The answer from this matrix is `gpt-5-nano word_only`.

## Verification

- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
- live matrix artifact:
  - `/tmp/lexicon-prompt-benchmark-20260315-curated100-schemafixed/summary.json`

