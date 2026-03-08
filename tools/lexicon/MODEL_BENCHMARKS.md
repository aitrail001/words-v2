# Lexicon Model Benchmarks

This document records the March 7, 2026 lexicon enrichment benchmark runs against the configured custom OpenAI-compatible gateway.

## Purpose

The lexicon admin tool has two distinct quality problems:

1. **Sense selection quality** — which WordNet-backed meanings are selected for learner-facing enrichment.
2. **Enrichment model quality** — how well the LLM turns an already-selected sense into learner-facing JSON.

These benchmarks measure **enrichment model quality only** on fixed prompts. They do **not** prove that a model fixes bad upstream sense ranking for words like `break` or weaker adjective picks like `open`.

## Test Setup

- **Gateway mode:** OpenAI-compatible custom gateway via the Node transport
- **Base URL:** operator-provided custom endpoint in local env
- **Transport:** Node OpenAI SDK path (`openai_compatible_node` style transport)
- **Reasoning effort:** `low`
- **Schema target:** the lexicon enrichment JSON schema produced by `tools/lexicon/enrich.py`
- **Prompt construction:** same `build_enrichment_prompt()` path used by the lexicon tool
- **System prompt:** same `_SYSTEM_PROMPT` used by the real enrichment pipeline
- **Validation:** outputs were parsed and validated through `_validate_openai_compatible_payload()`

## Models Compared

- `gpt-5.1`
- `gpt-5.2`
- `gpt-5.3`
- `gpt-5.4`

## Prompt Sets

### 4-prompt set

Representative mixed-POS set from the current lexicon snapshot:

- `right` / adjective
- `open` / adjective
- `direct` / adjective
- `break` / verb

Artifacts:

- `/tmp/lexicon-model-compare/gpt-5.1.json`
- `/tmp/lexicon-model-compare/gpt-5.2.json`
- `/tmp/lexicon-model-compare/gpt-5.3.json`
- `/tmp/lexicon-model-compare/gpt-5.4.json`

### 14-prompt set

Broader lexicon-style set covering verbs, nouns, and adjectives:

- `run` / verb
- `set` / noun
- `light` / noun
- `light` / adjective
- `right` / adjective
- `clear` / adjective
- `open` / adjective
- `direct` / adjective
- `present` / adjective
- `bank` / noun
- `record` / verb
- `break` / verb
- `play` / noun
- `subject` / noun

Artifacts:

- `/tmp/lexicon-model-compare-14/gpt-5.1.json`
- `/tmp/lexicon-model-compare-14/gpt-5.2.json`
- `/tmp/lexicon-model-compare-14/gpt-5.3.json`
- `/tmp/lexicon-model-compare-14/gpt-5.4.json`

## Quality Conclusions

### Overall ranking

Across both the 4-prompt and 14-prompt runs:

- **Best overall:** `gpt-5.4`
- **Very close second:** `gpt-5.3`
- **Solid fallback:** `gpt-5.1`
- **Weakest:** `gpt-5.2`

Short form:

- `gpt-5.4 ≈ gpt-5.3 > gpt-5.1 > gpt-5.2`

### Why

- `gpt-5.4` was the most consistently learner-friendly: concise definitions, strong usage notes, and the cleanest disambiguation.
- `gpt-5.3` was almost as strong as `gpt-5.4`, often with slightly plainer phrasing and shorter notes.
- `gpt-5.1` held up surprisingly well and is a legitimate fallback when quality matters less than speed/cost.
- `gpt-5.2` was consistently weaker: lower confidence, more verbosity, and less consistent pedagogical phrasing.

### Important examples

- **`right` adjective:** `gpt-5.3` and `gpt-5.4` gave the best directional explanations and usage notes.
- **`direct` adjective:** `gpt-5.4` had the strongest disambiguation from the verb sense; `gpt-5.3` was close.
- **`open` adjective:** all models were constrained by the weaker upstream selected adjective sense; this remains a sense-selection problem more than an LLM problem.
- **`break` verb:** all models handled the harsh “force into obedience” sense competently, but this remains a poor learner-first sense choice upstream.

## 4-Prompt Metrics

| Model | Avg confidence | Avg definition chars | Avg usage-note chars |
|---|---:|---:|---:|
| `gpt-5.1` | `0.903` | `95.5` | `315.0` |
| `gpt-5.2` | `0.800` | `141.8` | `265.8` |
| `gpt-5.3` | `0.935` | `88.0` | `162.5` |
| `gpt-5.4` | `0.945` | `90.2` | `249.2` |

## 14-Prompt Metrics

| Model | Avg confidence | Avg definition chars | Avg usage-note chars |
|---|---:|---:|---:|
| `gpt-5.1` | `0.906` | `95.9` | `373.1` |
| `gpt-5.2` | `0.840` | `113.2` | `282.6` |
| `gpt-5.3` | `0.940` | `87.4` | `191.6` |
| `gpt-5.4` | `0.948` | `80.4` | `249.3` |

### 14-Prompt CEFR distributions

- `gpt-5.1`: `A1×3`, `A2×2`, `B1×8`, `C1×1`
- `gpt-5.2`: `A1×3`, `A2×4`, `B1×5`, `B2×1`, `C1×1`
- `gpt-5.3`: `A1×4`, `A2×3`, `B1×6`, `C1×1`
- `gpt-5.4`: `A1×3`, `A2×5`, `B1×5`, `C1×1`

Interpretation:

- `gpt-5.2` was the least stable in CEFR calibration.
- `gpt-5.3` and `gpt-5.4` stayed more consistent and usually produced the tightest learner-level fit.

## Latency Notes

A second 14-prompt run was executed with all four models in parallel to capture wall-clock timing under **shared gateway load**.

Measured batch durations under that parallel load:

- `gpt-5.1` → `106s` for 14 prompts
- `gpt-5.2` → `218s` for 14 prompts
- `gpt-5.3` → `172s` for 14 prompts
- `gpt-5.4` → `134s` for 14 prompts

Interpretation:

- These timings are useful for **relative ranking under concurrent load**, not exact serial capacity planning.
- Gateway contention and upstream rate shaping materially affect these numbers.
- Even under shared load, `gpt-5.2` was still the slowest and least attractive quality/speed tradeoff.

### Operational takeaway

- **Best quality / still practical:** `gpt-5.4`
- **Best quality/speed balance:** `gpt-5.3` or `gpt-5.4`
- **Best fallback when quality can drop:** `gpt-5.1`
- **Avoid unless there is a strong external reason:** `gpt-5.2`

## 20k-Word Planning Caveat

The lexicon pipeline enriches **selected senses**, not just words.

In the current 51-word sample, the selector produced about **5.84 senses per word** on average.

That means a 20k-word batch is closer to **~116,800 enrichment prompts** than 20,000 prompts.

Because gateway throughput depends heavily on concurrency, queueing, retries, and model latency variance, this benchmark should be used for:

- **model choice**, and
- **relative speed expectations**

but not as a final exact ETA calculator without a controlled throughput test for the target deployment settings.

## Recommendation

Use:

- **Primary model:** `gpt-5.4`
- **Fallback model:** `gpt-5.3`
- **Budget fallback:** `gpt-5.1`

Do not treat `gpt-5.2` as the default choice for this lexicon enrichment workflow.

## Remaining Gap

These benchmarks do not solve upstream sense-selection problems. The two biggest remaining areas are:

- broad verb ranking for words like `break`
- adjective quality/ordering for words like `open` and `close`

Those should be improved in the selector independently of model choice.
