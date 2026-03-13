# Lexicon Robustness 5K Benchmark Design

Date: 2026-03-13

## Goal

Create one deterministic 5K benchmark that exercises the non-LLM `build-base` path across realistic common-word traffic and known boundary classes, then use that run to judge whether the deterministic path is ready to scale toward 30K words.

## Recommended Composition

Use a union-plus-expansion strategy:

1. Start from the four tracked 1K benchmark lists already in the repo:
   - `tricky_common_1000_20260313`
   - `morphology_edge_1000_20260313`
   - `semantic_ambiguity_1000_20260313`
   - `tricky_words_1000_20260313`
2. Dedupe that base union while preserving source-order coverage.
3. Expand the union to 5K with deterministic boundary candidates drawn from:
   - short `-s/-es/-ies` endings
   - proper-name/surname-like forms ending in `s`
   - invariant plurals and plural-only common forms
   - currencies and unit plurals
   - lexicalized derivatives and morphology/semantics border cases
   - additional common top-frequency words from `wordfreq`

## Why This Shape

- The tracked 1K lists already cover the main known classes and should stay part of the readiness signal.
- A pure top-5K list is realistic but weak for diagnosis.
- A pure edge-case list is useful for debugging but not representative enough for a 30K-readiness claim.
- This mixed 5K list keeps realism while amplifying the tails that previously caused deterministic mistakes.

## Success Criteria

The deterministic path is “ready enough to attempt 30K without LLM in the base stage” if:

- no large new class of obviously bogus selected canonical links appears
- ambiguous tails stay bounded relative to list size
- valid morphology-linked cases still survive
- remaining issues are isolated edge classes rather than bulk false-link patterns

## Failure Signals

Treat the run as not ready if any of the following appears:

- a broad family of weak chopped stems becomes selected again
- many common high-frequency words fall into `unknown_needs_llm`
- valid inflectional collapse regresses across ordinary words
- candidate tails reveal a systematic deterministic bug likely to scale with corpus size
