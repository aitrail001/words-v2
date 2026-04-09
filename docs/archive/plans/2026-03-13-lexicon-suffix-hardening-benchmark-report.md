# Lexicon Suffix Hardening Benchmark Report

Date: 2026-03-13

## Scope

This report covers deterministic `build-base` output after the suffix hardening follow-up in `fix_lexicon_suffix_hardening_20260313`.

Datasets:

- `tricky_common_1000_20260313`
- `morphology_edge_1000_20260313`
- `semantic_ambiguity_1000_20260313`
- `suffix_risk_1000_20260313`
- `short_stem_risk_1000_20260313`

No LLM enrichment or adjudication was used.

## What Changed

The canonicalizer now applies two conservative guards:

1. plain trailing-`s` no longer generates weak double-`s` chops such as `pass -> pas` or `boss -> bos`
2. plural-style suffix candidates (`-s`, `-es`, `-ies`) are only kept when the morphology candidate has lexical label support from the surface senses, the candidate senses, or both

This keeps real morphology candidates such as `thing`, `give`, `peso`, and `rupee`, while removing junk stems such as `thi`, `chri`, `itun`, `forb`, `seri`, and `mony`.

## Snapshot Summary

| Dataset | Lexemes | Senses | Ambiguous tails | `keep_separate` | `keep_both_linked` | `collapse_to_canonical` | `unknown_needs_llm` |
|---|---:|---:|---:|---:|---:|---:|---:|
| tricky common | 1000 | 4378 | 0 | 557 | 443 | 0 | 0 |
| morphology edge | 950 | 4025 | 2 | 157 | 597 | 244 | 2 |
| semantic ambiguity | 998 | 4446 | 2 | 825 | 173 | 0 | 2 |
| suffix risk | 999 | 4006 | 1 | 66 | 933 | 0 | 1 |
| short stem risk | 989 | 3628 | 5 | 253 | 105 | 637 | 5 |

## Original Three Benchmark Sets

Behavior changes versus the pre-fix snapshots were limited to two words in all three original 1K sets:

- `pass`: `keep_both_linked -> keep_separate`, removed invalid `linked_canonical_form = pas`
- `boss`: `keep_both_linked -> keep_separate`, removed invalid `linked_canonical_form = bos`

No other `canonical_form` / `decision` / `linked_canonical_form` changes were introduced in those three sets.

## Expanded Benchmark Sets

### `suffix_risk_1000_20260313`

- `ambiguous_form_count = 1`
- only remaining ambiguous item: `rupees -> rupee`
- known bad direct links such as `pass -> pas`, `glass -> glas`, and `class -> clas` no longer appear as selected links

### `short_stem_risk_1000_20260313`

- pre-hardening state: `ambiguous_form_count = 131`
- final state: `ambiguous_form_count = 5`
- removed bogus candidates include:
  - `this -> thi`
  - `his -> hi`
  - `chris -> chri`
  - `versus -> versu`
  - `itunes -> itun`
  - `series -> seri/sery`
  - `monies -> mony/moni`

Remaining ambiguous items:

- `pesos -> peso`
- `rupees -> rupee`
- `perks -> perk`
- `torres -> torr`
- `hines -> hin`

The first two are legitimate singular/plural tails. The last three are isolated real-word/surname overlaps rather than the mass weak-stem failure class that originally dominated this dataset.

## Probe Outcomes

Preserved as intended:

- `things -> thing`
- `gives -> give`
- `added -> add`
- `coming -> come`
- `meeting` stays linked to `meet`
- `left` stays linked to `leave`

No longer linked as selected morphology:

- `pass -> pas`
- `boss -> bos`
- `glass -> glas`
- `class -> clas`
- `this -> thi`
- `his -> hi`
- `chris -> chri`
- `versus -> versu`

## Verification

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_canonical_forms.py tools/lexicon/tests/test_form_adjudication.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

Each benchmark snapshot was rebuilt locally with `tools.lexicon.cli build-base --rerun-existing` against the corresponding benchmark word list.
