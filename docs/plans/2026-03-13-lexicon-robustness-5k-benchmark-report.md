# Lexicon Robustness 5K Benchmark Report

Date: 2026-03-13
Owner: Codex
Scope: Deterministic `build-base` robustness benchmark with no LLM/adjudication

## Summary

The mixed 5K benchmark is now in a "mostly ready with bounded tails" state for scaling toward the planned 30K rollout.

The benchmark no longer shows broad deterministic chopped-stem drift. The remaining unresolved tail is narrow: eight `unknown_needs_llm` rows out of 5000 inputs, dominated by currency plurals and name/place-like `-s/-es` forms rather than systemic suffix breakage.

One additional generic hardening pass was required during this benchmark run. A non-plural suffix filter initially removed junk tails such as `during -> dur` and `whether -> wheth`, but it also regressed valid inflection handling for cases like `ringed -> ring` when sense support was absent. The final fix keeps non-plural suffix candidates when they have explicit sense support or a real frequency rank that is at least as good as the surface form, which restores valid inflection ambiguity handling without reopening unknown chopped stems.

## Benchmark Composition

Input list: `data/lexicon/benchmarks/robustness_border_5000_20260313.txt`

Machine-readable summary: `data/lexicon/benchmarks/robustness_border_5000_20260313.summary.json`

Source mix:

- `tricky_common`: 1000
- `morphology_edge`: 540
- `semantic_ambiguity`: 242
- `tricky_words`: 19
- `curated_invariant_plurals`: 34
- `curated_currency_units`: 35
- `curated_lexicalized_derivatives`: 18
- `curated_name_like`: 77
- `auto_short_s_risk`: 700
- `auto_es_ies_risk`: 700
- `auto_classical_s_endings`: 269
- `top_frequency_filler`: 1366

The benchmark starts from a deduplicated 1801-word union of existing tracked benchmark sets, then fills to 5000 with deterministic risk-heavy and high-frequency coverage so it exercises both realistic rollout traffic and known suffix/morphology boundary classes.

## Verification Evidence

Commands run in `/Users/johnson/AI/src/words-v2/.worktrees/benchmark_lexicon_robustness_5k_20260313`:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_form_adjudication.py tools/lexicon/tests/test_canonical_forms.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
/usr/bin/time -p /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli build-base --rerun-existing --output-dir data/lexicon/snapshots/robustness-border-5000-20260313 $(cat data/lexicon/benchmarks/robustness_border_5000_20260313.txt)
```

Observed results:

- Targeted canonicalization/form-adjudication tests: `18 passed in 0.12s`
- Full lexicon suite: `195 passed in 3.42s`
- Real-provider deterministic 5K build: `real 8.88s`

Snapshot summary from `data/lexicon/snapshots/robustness-border-5000-20260313`:

- `lexeme_count=4080`
- `sense_count=13862`
- `concept_count=13563`
- `ambiguous_form_count=8`

Decision counts from `canonical_variants.jsonl`:

- `keep_separate=2842`
- `collapse_to_canonical=1551`
- `keep_both_linked=599`
- `unknown_needs_llm=8`

## Before / After Hardening

Earlier 5K run before the latest generic filter correction:

- `real 8.74s`
- `lexeme_count=4075`
- `sense_count=13857`
- `concept_count=13563`
- `ambiguous_form_count=13`

Suspicious deterministic behavior seen before the final fix:

- bad selected links: `james -> jam`, `dulles -> dull`, `mars -> mar`, `gates -> gate`
- bad chopped tails lingering as candidates: `something -> someth`, `anything -> anyth`, `everything -> everyth`, `during -> dur`, `whether -> wheth`

After the final hardening:

- all of those probe words now resolve to `keep_separate`
- the chopped-tail candidates above are removed entirely
- the ambiguous tail shrank from `13` to `8`
- valid inflection behavior still survives, including `added -> add`, `coming -> come`, and deferred ambiguity handling for `ringed -> ring`

## Probe Audit

Confirmed safe outcomes:

- `james`: `keep_separate`
- `dulles`: `keep_separate`
- `mars`: `keep_separate`
- `gates`: `keep_separate`
- `something`: `keep_separate`, no suffix candidates left
- `anything`: `keep_separate`, no suffix candidates left
- `everything`: `keep_separate`, no suffix candidates left
- `during`: `keep_separate`, no suffix candidates left
- `whether`: `keep_separate`, no suffix candidates left
- `pass`: `keep_separate`
- `boss`: `keep_separate`
- `series`: `keep_separate`
- `things`: `keep_separate` when it has its own learner-worthy meaning
- `works`: `keep_separate`

Confirmed valid positive morphology still works:

- `added -> add`
- `coming -> come`
- `ringed -> ring` remains detectable as an ambiguous deterministic tail instead of being silently dropped

## Remaining Ambiguous Tail

`ambiguous_forms.jsonl` now contains exactly:

- `rupees -> rupee`
- `pesos -> peso`
- `dirhams -> dirham`
- `torres -> torr`
- `hines -> hin`
- `perks -> perk`
- `sanders -> sander`
- `angeles -> angel`

Interpretation:

- `rupees`, `pesos`, and `dirhams` are legitimate singular/plural-style cases that may reasonably remain in the bounded ambiguous/adjudication path.
- `torres`, `hines`, `sanders`, and `angeles` are name/place-like cases where a generic suffix rule still surfaces a plausible-looking but wrong tail.
- `perks -> perk` is borderline because both surface and candidate are real words, but deterministic evidence remains intentionally too weak to collapse it.

## Readiness Judgment

Judgment: mostly ready with bounded tails

Rationale:

1. The remaining unknown tail is tiny relative to the benchmark size: `8 / 5000` inputs, or `0.16%`.
2. The unresolved cases are concentrated in narrow classes rather than spread across common words, suggesting there is no broad deterministic collapse bug left in the current suffix pipeline.
3. The operator path for unresolved ambiguity already exists and is a better fit for this residual class than more aggressive deterministic guessing.
4. The benchmark still preserves the user-required policy boundary: collapse only true inflectional/morphological variants, keep lexicalized or independently meaningful forms separate.

Residual caution before a full 30K run:

- Expect the same bounded name/place/currency tail class to recur at larger scale.
- The 30K rollout should keep ambiguous-tail detection/adjudication enabled and should be monitored for growth beyond this narrow profile.

## Recommended Next Step

Proceed to the next larger deterministic rollout stage with the current hardening in place, but treat `ambiguous_forms.jsonl` as an expected review artifact rather than trying to fully eliminate this tail deterministically before scaling.
