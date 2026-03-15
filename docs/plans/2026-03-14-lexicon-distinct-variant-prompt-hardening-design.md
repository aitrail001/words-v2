# Lexicon Distinct-Variant Prompt Hardening Design

Date: 2026-03-14
Owner: Codex

## Goal

Mark words like `building`, `charming`, and `ceiling` as distinct derived entries when they are not just plain inflectional forms of a base word, so the later LLM enrichment prompt links them to the base word briefly and then focuses only on their standalone meanings.

## Problem

The deterministic lexicon pipeline already preserves some linked lexicalized forms as separate learner entries and already carries entity categories such as `name`, `place`, `brand`, and `entity_other`.

However, there is still a gap for words that look like predictable derived or inflected forms from the surface shape, but function as their own learner-worthy noun/adjective entries:

- `building` is not only “the act of build”
- `charming` is not only “currently charm-ing”
- `ceiling` is not only a productive `-ing` form of `ceil`

If these words are prompted like ordinary general entries, the LLM can duplicate the base-word meanings instead of generating:

1. a short note that the word is related to the base word, and
2. only the distinct standalone meanings for the derived word.

## Requirements

1. Use explicit tracked data when we have audited knowledge about a word/base relationship.
2. Fall back to bounded deterministic inference when no explicit dataset row exists.
3. Keep the behavior generic, not hardcoded per example.
4. Keep entity-category handling for `name`, `place`, `brand`, and `entity_other`.
5. Avoid widening canonical collapse logic. This is prompt guidance metadata, not more aggressive deduplication.

## Chosen Approach

### 1. Add a tracked dataset for distinct-meaning derived variants

Create a dedicated JSON dataset for explicit rows such as:

- surface word
- base word
- relationship label
- reason
- optional prompt note

This dataset is authoritative when present.

Examples:

- `building -> build`
- `charming -> charm`
- `ceiling -> ceil`

This keeps policy data out of code and lets us expand coverage without logic edits.

### 2. Add bounded inference for uncovered cases

When a word is not in the explicit dataset, infer distinct-derived-entry metadata conservatively.

The inference should only fire when all of these are true:

- the surface word plausibly reduces to a valid base word by a bounded derivational pattern already relevant to learner vocabulary, such as select `-ing`, `-ed`, or similar productive shapes
- the surface word remains its own canonical learner entry rather than collapsing away
- the surface word has standalone noun/adjective/adverb senses that are not just the ordinary base-word event/state reading

The inference is a fallback, not the primary policy path.

### 3. Carry stronger metadata on lexeme rows

Extend the interim lexeme metadata beyond the current generic linked-variant flag so later prompt generation can distinguish:

- ordinary general entries
- named-entity categories
- variant-linked entries with distinct standalone meanings

This metadata should support prompt behavior, auditability, and future import/reporting.

### 4. Tighten the per-word enrichment prompt

For distinct-derived entries:

- say the word is another form or derivative related to base word `X`
- tell the model not to regenerate the ordinary meanings already covered by `X`
- tell the model to include only the distinct meanings/usages that justify keeping the surface word as its own learner entry
- require a short usage note that links the word to the base form

This should apply to both the normal per-word prompt and the repair prompt.

### 5. Preserve entity-category-aware prompting

The existing entity categories are already the right families:

- `general`
- `name`
- `place`
- `brand`
- `entity_other`

This slice should keep that path intact and make sure the prompt continues to steer the model away from broadening a proper noun or brand into unrelated common-word meanings.

## Why This Approach

- It matches the existing repo direction: tracked policy data first, deterministic logic second.
- It solves the prompt problem without overcomplicating canonicalization.
- It keeps the later LLM stage aligned with deterministic lexeme metadata.
- It is extensible: more audited rows can be added in data files without code churn.

## Non-Goals

- Do not change the final 30K selection boundary in this slice unless tests or docs need refresh.
- Do not run the real LLM enrichment stage yet.
- Do not broaden canonical collapse to merge more words together.

## Success Criteria

1. The code can mark distinct-derived entries from an explicit dataset.
2. The code can infer additional distinct-derived entries conservatively when no explicit row exists.
3. The per-word prompt tells the LLM to link to the base word and avoid duplicating base meanings.
4. Entity-category guidance still appears for places, names, brands, and other non-general entities.
5. Lexicon tests cover explicit-dataset wins, inference fallback, and prompt wording.
