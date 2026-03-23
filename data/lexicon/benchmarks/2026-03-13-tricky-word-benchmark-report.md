# Tricky Word Benchmark Report

Date: 2026-03-13

## Scope

Generated and tested three 1000-word benchmark sets against the current `main` branch canonicalization logic after the morphology-only collapse fix:

- `tricky_common_1000_20260313`
- `morphology_edge_1000_20260313`
- `semantic_ambiguity_1000_20260313`

No LLM or enrichment run was used. This report covers `build-base` behavior only.

## Artifacts

Benchmark lists:

- `data/lexicon/benchmarks/tricky_common_1000_20260313.txt`
- `data/lexicon/benchmarks/morphology_edge_1000_20260313.txt`
- `data/lexicon/benchmarks/semantic_ambiguity_1000_20260313.txt`

Scored metadata:

- `data/lexicon/benchmarks/tricky_common_1000_20260313.json`
- `data/lexicon/benchmarks/morphology_edge_1000_20260313.json`
- `data/lexicon/benchmarks/semantic_ambiguity_1000_20260313.json`

Snapshot outputs:

- `data/lexicon/snapshots/tricky-common-1000-20260313`
- `data/lexicon/snapshots/morphology-edge-1000-20260313`
- `data/lexicon/snapshots/semantic-ambiguity-1000-20260313`

## Commands Run

```bash
PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli build-base $(cat data/lexicon/benchmarks/tricky_common_1000_20260313.txt) --output-dir data/lexicon/snapshots/tricky-common-1000-20260313

PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli build-base $(cat data/lexicon/benchmarks/morphology_edge_1000_20260313.txt) --output-dir data/lexicon/snapshots/morphology-edge-1000-20260313

PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli build-base $(cat data/lexicon/benchmarks/semantic_ambiguity_1000_20260313.txt) --output-dir data/lexicon/snapshots/semantic-ambiguity-1000-20260313
```

## Summary Table

| Dataset | Lexemes | Senses | Ambiguous Tails | `keep_separate` | `keep_both_linked` | `collapse_to_canonical` | `unknown_needs_llm` |
|---|---:|---:|---:|---:|---:|---:|---:|
| tricky common | 1000 | 4378 | 0 | 555 | 445 | 0 | 0 |
| morphology edge | 950 | 4025 | 2 | 155 | 599 | 244 | 2 |
| semantic ambiguity | 998 | 4446 | 2 | 823 | 175 | 0 | 2 |

## Interpretation

### 1. Tricky common set

This set is good for broad regression testing of common learner-facing words with high polysemy and lexicalized related forms.

Strong signals:

- many linked-but-preserved forms such as `going -> go`, `better -> good`, `left -> leave`, `given -> give`, `meeting -> meet`
- zero deterministic collapses
- zero ambiguous tails in this exact slice

Use this set when you want to verify that common tricky words do not get over-collapsed.

### 2. Morphology edge set

This is the best stress set for the morphology-only collapse policy.

Strong signals:

- `244` deterministic collapses, mostly clean inflectional cases like `coming -> come`, `taking -> take`, `supporting -> support`
- `599` linked standalone forms where morphology exists but the surface form still stays as its own headword
- only `2` ambiguous tails

Use this set to test whether inflectional collapse is still working after canonicalization changes.

### 3. Semantic ambiguity set

This is the best set for guarding against the original bug class.

Strong signals:

- `823` `keep_separate`
- `0` deterministic collapses
- only `175` linked forms
- canonical trouble words like `out`, `good`, `first`, `back`, `go`, `right`, `total` all stay separate

Use this set to make sure semantic neighbors do not collapse just because WordNet labels are related.

## Good Outcomes Confirmed

- `almost` stays separate
- `total` stays separate
- `add` stays separate
- `added -> add` still collapses
- `meeting -> meet` stays linked, not collapsed
- `left -> leave` stays linked, not collapsed
- `coming -> come` and `taking -> take` still collapse in the morphology-focused set

## Residual Issues

### Suspicious linked form: `pass -> pas`

This appears in all three benchmark snapshots as:

- `decision = keep_both_linked`
- `linked_canonical_form = pas`

This is not a valid learner-facing lexical relation. It looks like a false suffix-derived morphology candidate leaking through the linking path.

This is the clearest follow-up bug exposed by the new benchmark runs.

### Ambiguous currency plurals

Both `morphology_edge` and `semantic_ambiguity` surfaced:

- `rupees`
- `pesos`

These land in `unknown_needs_llm` with empty `sense_labels` and bounded candidate forms. That behavior is acceptable for now, but it suggests some currency plurals are under-grounded by the current lexical providers.

## Recommendation

Use all three sets, but for different gates:

- `tricky_common_1000_20260313` for broad common-word regression checks
- `morphology_edge_1000_20260313` for collapse/link behavior after canonicalization changes
- `semantic_ambiguity_1000_20260313` for guarding against semantic over-collapse

Immediate follow-up worth doing:

1. tighten the suffix heuristic or linking gate so invalid links like `pass -> pas` cannot survive
2. keep the semantic ambiguity set as a permanent no-regression benchmark
3. optionally add a small currency/units tail benchmark for words like `pesos` and `rupees`
