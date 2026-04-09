# Real 30K Curation And Variant Enrichment Design

Date: 2026-03-14
Owner: Codex

## Goal

Produce a real deterministic 30K common-word snapshot from `wordfreq` after canonical collapse, while preserving separately learner-worthy lexicalized variants as distinct headwords and marking them so the later LLM enrichment step does not duplicate the base-word meanings.

## Problem

The current deterministic pipeline can keep words like `left`, `meeting`, or lexicalized plural-like forms as separate headwords when they have their own meanings, but the downstream enrichment path does not know that these entries are also variant-linked to a base form. Without explicit metadata, the later LLM prompt may regenerate the base-word meanings instead of focusing only on the distinct meanings for the surface form.

Separately, a real 30K rollout cannot simply request the top 30K `wordfreq` tokens because deterministic canonical collapse removes some forms. The output snapshot must contain 30,000 surviving canonical headwords, not just 30,000 requested source tokens.

## Chosen Approach

### 1. Carry lexicalized-variant metadata in `lexemes.jsonl`

Add explicit variant metadata to `LexemeRecord`, which is already the interim row consumed by `enrich`.

For headwords that remain separate but are linked to a base form because they have their own meanings:

- `variant_base_form`: linked base lemma
- `variant_relationship`: stable relationship label, initially `lexicalized_form`
- `is_variant_with_distinct_meanings`: boolean gate for prompt behavior

This metadata will be populated from deterministic canonicalization/build-base decisions, not inferred later.

### 2. Use variant-aware enrichment prompts

For ordinary lexemes, keep the current prompt behavior.

For variant-linked lexemes with distinct meanings:

- explicitly tell the model the word is another form of the base word
- instruct it not to repeat the ordinary meanings already covered by the base word
- instruct it to generate only the meanings that are distinct/special to the surface form
- require a short usage note that makes the relationship to the base word clear

This keeps the word in the final 30K list while sharply reducing duplicate enrichment.

### 3. Curate the real 30K list by post-collapse count, not request count

Drive the existing deterministic `build-base --top-words N --rerun-existing` path in a bounded outer loop.

Process:

1. Request an initial top-word window from `wordfreq`.
2. Run deterministic `build-base`.
3. Measure surviving `lexeme_count`.
4. Expand or shrink the requested window until the snapshot lands on exactly 30,000 surviving lexemes.

This uses the production CLI path as the source of truth and automatically “selects the next available one” whenever a requested token collapses away.

## Why This Approach

- It keeps canonicalization, snapshot generation, and enrichment aligned on one deterministic source of truth.
- It avoids ad hoc later reconstruction of variant relationships from sidecars.
- It does not change the user’s desired policy boundary: lexicalized forms still count as separate words in the final 30K list.
- It requires only a small schema extension and prompt extension, not a redesign of the enrichment output format.

## Non-Goals

- Do not run LLM enrichment in this slice.
- Do not change the compiled export schema yet unless needed for downstream integrity.
- Do not try to eliminate all ambiguous-form tails before the 30K deterministic snapshot is produced.

## Success Criteria

1. `lexemes.jsonl` rows for linked-but-separate lexicalized variants carry explicit variant metadata.
2. Variant-aware prompt tests show the LLM instruction contains the “do not duplicate base meanings” guidance.
3. Existing deterministic canonicalization behavior remains intact.
4. A new dated snapshot directory contains a real post-collapse 30,000-word deterministic base set ready for the later LLM stage.
