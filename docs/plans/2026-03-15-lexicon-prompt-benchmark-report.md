# Lexicon Prompt Benchmark Report

Date: 2026-03-15
Owner: Codex

## Goal

Compare live speed and output quality for the lexicon per-word enrichment path across:

- `gpt-5.1-chat`
- `gpt-5.1`
- `gpt-5.4`

and across two prompt modes:

- `word_only`
- `grounded`

## Important Scope Note

This benchmark compares:

- a bare word prompt with only allowed `sense_id` anchors, versus
- the existing lexicon grounded prompt with selected WordNet sense context

It does **not** compare against a true "full WordNet candidate pool" prompt. The grounded mode here is the production-style selected-sense grounding path from `tools/lexicon/enrich.py`.

## Benchmark Setup

- Transport: `openai_compatible_node`
- Base URL: operator-provided custom gateway
- Shared schema/validator: existing lexicon per-word JSON schema and `_validate_openai_compatible_word_payload()`
- Prompt modes:
  - `word_only`
  - `grounded`
- Small tracked live set: `["right", "break", "building", "kinshasa"]`
  - mixed POS
  - common polysemy
  - distinct-derived variant entry
  - named-entity entry

Artifacts:

- `gpt-5.1-chat` small-set runs: `/tmp/lexicon-prompt-benchmark-20260315-small4`
- `gpt-5.1` small-set runs: `/tmp/lexicon-prompt-benchmark-20260315-gpt51-small4`
- partial larger-set `gpt-5.1-chat` runs: `/tmp/lexicon-prompt-benchmark-20260315`

### Tracked 100-word benchmark set

The repo now also carries a fixed `curated_100` dataset for broader repeatable benchmark work:

- word list: `tools/lexicon/benchmarks/enrichment_prompt_words_100.json`
- metadata: `tools/lexicon/benchmarks/enrichment_prompt_words_100.meta.json`
- deterministic rubric support in: `tools/lexicon/enrichment_benchmark.py`

Category mix:

- `common_polysemous`: `25`
- `noun_verb_crossover`: `20`
- `adj_adv_ambiguity`: `15`
- `distinct_variant`: `15`
- `entity`: `10`
- `harder_tail`: `15`

This set is validated in tests for exact size, uniqueness, and metadata alignment, and the benchmark summary now records both `category_counts` and a lightweight rubric summary for each run:

- `dropped_row_count`
- `distinct_variant_rows`
- `distinct_variant_linked_note_hits`
- `entity_rows`
- `entity_specific_note_hits`
- `suspicious_generated_forms`

## Live Results

### Small 4-word set

| Model | Prompt mode | Batch seconds | Avg lexeme seconds | Valid rows | Avg confidence | Avg definition chars | Avg usage-note chars |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gpt-5.1-chat` | `word_only` | `98.914` | `24.728` | `17/17` | `0.938` | `71.7` | `120.8` |
| `gpt-5.1-chat` | `grounded` | `75.489` | `18.872` | `15/17` | `0.916` | `80.2` | `120.7` |
| `gpt-5.1` | `word_only` | `111.567` | `27.891` | `17/17` | `0.934` | `67.8` | `123.7` |
| `gpt-5.1` | `grounded` | `79.133` | `19.783` | `15/17` | `0.909` | `74.9` | `143.2` |
| `gpt-5.4` | `word_only` | `179.414` | `44.853` | `16/17` | `0.924` | `55.9` | `89.3` |
| `gpt-5.4` | `grounded` | `177.370` | `44.342` | `15/17` | `0.873` | `62.3` | `120.8` |

### Larger 8-word set

The larger 8-word batch completed only for `gpt-5.1-chat` within the practical benchmark window:

| Model | Prompt mode | Batch seconds | Avg lexeme seconds | Valid rows | Avg confidence |
|---|---:|---:|---:|---:|---:|
| `gpt-5.1-chat` | `word_only` | `189.655` | `23.706` | `39/39` | `0.942` |
| `gpt-5.1-chat` | `grounded` | `162.328` | `20.291` | `37/39` | `0.914` |

Operational note:

- the original 8-word `gpt-5.4` run failed at the default `60s` timeout
- `gpt-5.4` required raising `LEXICON_LLM_TIMEOUT_SECONDS` to `180` even for the small-set completion

## What Changed With Grounding

### Speed

Contrary to the naive expectation that a shorter prompt should always be faster, the grounded prompt was faster than `word_only` for both `gpt-5.1-chat` and `gpt-5.1`.

Observed on the 4-word set:

- `gpt-5.1-chat`: `75.5s grounded` vs `98.9s word_only`
- `gpt-5.1`: `79.1s grounded` vs `111.6s word_only`
- `gpt-5.4`: nearly flat, `177.4s grounded` vs `179.4s word_only`

Interpretation:

- the grounding context appears to reduce search/disambiguation work for the smaller models
- removing the semantic grounding did not buy latency in this setup

### Quality

`word_only` tends to preserve total valid row count slightly better, but that is not the whole quality story.

The grounded prompt consistently gave better semantic steering on:

- named-entity behavior like `kinshasa`
- base-word linkage for derived entries like `building`
- narrower domain targeting for harder senses

Representative examples:

- `gpt-5.1 grounded` on `kinshasa` explicitly treated it as a proper noun and added location/travel guidance rather than a generic city gloss
- `gpt-5.1 grounded` on `building` explicitly explained the relation to base word `build` while keeping the noun meaning separate
- `gpt-5.4 grounded` did improve entity guidance, but it also produced a clear form-generation error for `building` (`buildinged` verb forms), which is a quality regression

## Model Comparison

### `gpt-5.1-chat`

Strengths:

- fastest completed model on both the 4-word and 8-word sets
- stable and concise output
- no repair loops in grounded mode
- operationally viable for batch work

Weaknesses:

- grounded mode dropped some selected rows (`15/17` on the 4-word set, `37/39` on the 8-word set)
- quality is solid, but not obviously better than `gpt-5.1` on the harder entity/variant notes

### `gpt-5.1`

Strengths:

- slower than `gpt-5.1-chat`, as expected, but still far faster than `gpt-5.4`
- grounded mode produced the strongest overall balance on this benchmark:
  - good entity handling
  - good variant-aware explanations
  - practical batch latency

Weaknesses:

- `word_only` needed one repair cycle
- still dropped to `15/17` valid rows in grounded mode

### `gpt-5.4`

Strengths:

- can produce concise outputs
- grounded mode still gave good named-entity framing on `kinshasa`

Weaknesses:

- clearly the slowest model on this gateway
- default timeout was not sufficient for the larger batch
- grounded quality was not clearly superior to `gpt-5.1`
- produced at least one concrete form-quality regression (`buildinged`)

## Recommendation

### Best practical default

Use `gpt-5.1` with the grounded prompt.

Reason:

- faster than `gpt-5.4` by a large margin
- slower than `gpt-5.1-chat`, but still practical
- better qualitative steering than `word_only`
- better overall quality/speed tradeoff than `gpt-5.4` on this gateway

### Best throughput fallback

Use `gpt-5.1-chat` with the grounded prompt.

Reason:

- fastest completed grounded mode
- grounding improved speed instead of hurting it
- keeps the entity/variant steering that `word_only` loses

### Do not prefer `word_only`

For this lexicon workflow, `word_only` is not currently attractive as the default benchmark winner:

- it was slower than grounded for `gpt-5.1-chat` and `gpt-5.1`
- it reduces semantic steering for entities and derived variants
- it only wins narrowly on raw valid-row count, not on the overall learner-facing output quality

### Do not choose `gpt-5.4` as the operational default here

On this gateway and prompt path:

- it is much slower
- it needed a higher timeout
- it did not show enough quality gain to justify the runtime penalty

## 100-word matrix status

The full live `curated_100` matrix across `3 models x 2 prompt modes` is now operationally defined, but it was not executed end-to-end in this change set because the measured small-set latencies make it a multi-hour run on this gateway rather than a quick benchmark.

Using the observed small-set `Avg lexeme seconds` as the planning baseline:

- `gpt-5.1-chat grounded` projects to about `31.5 minutes` per 100-word run
- `gpt-5.1 grounded` projects to about `33.0 minutes` per 100-word run
- `gpt-5.4 grounded` projects to about `73.9 minutes` per 100-word run
- the full six-run matrix projects to roughly `3.2` to `7.5` hours wall-clock, depending on model mix and retry behavior

That is why this slice focused on:

- making the benchmark harness reproducible
- committing the fixed 100-word dataset and metadata
- adding deterministic rubric summaries for broader live runs
- re-verifying the lexicon suite after the prompt-mode and benchmark changes

The current recommendation still rests on the completed live 4-word and 8-word runs plus the now-verified larger benchmark harness.

## Verification

- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
- `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_enrichment_benchmark.py -q`
- live benchmark commands:
  - `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli benchmark-enrichment --output-dir /tmp/lexicon-prompt-benchmark-20260315-small4 --dataset /tmp/lexicon-prompt-benchmark-small4.json --provider-mode openai_compatible_node --prompt-mode word_only --prompt-mode grounded --model gpt-5.1-chat --model gpt-5.4`
  - `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli benchmark-enrichment --output-dir /tmp/lexicon-prompt-benchmark-20260315-gpt51-small4 --dataset /tmp/lexicon-prompt-benchmark-small4.json --provider-mode openai_compatible_node --prompt-mode word_only --prompt-mode grounded --model gpt-5.1`
