# Lexicon Learner-First Entry Sourcing Design

**Date:** 2026-03-11

## Goal

Replace the current over-engineered, WordNet-shaped mental model with a simpler learner-first lexicon design that:

1. builds a local offline English lexicon,
2. covers the top common single-word and multiword learner entries,
3. lets the LLM choose learner-friendly meanings with source grounding,
4. minimizes human review,
5. keeps the final product schema learner-facing rather than source-facing.

## Product principles

### 1. Entries, not synsets

The product should be built around learner entries, not around WordNet synsets.

A final lexicon entry is one of:
- `word`
- `phrasal_verb`
- `fixed_expression`
- `idiom`
- `formulaic_expression`

WordNet and other sources are internal grounding/context layers, not the product's public mental model.

### 2. LLM selects learner meanings

We should **not** manually select meanings/senses/definitions.

Instead:
- lexical sources provide candidate meaning context,
- the LLM chooses the top learner-friendly meanings,
- the LLM rewrites learner-facing definitions/examples/collocations into our schema,
- human review is reserved for a small unstable tail.

### 3. Human review is exceptional

The target workflow is high automation:
- deterministic filters and ranking handle inventory selection,
- LLM handles most meaning selection and enrichment,
- human review happens only when confidence is low or ambiguity is unusually high.

## Scope

This design covers the offline/admin lexicon builder only.

### In scope
- sourcing English entry candidates
- quota policy by entry type
- learner-first schema direction
- automated meaning selection strategy
- minimal-review policy
- offline/local DB target

### Out of scope
- commercial dictionary licensing integration
- frontend implementation details
- live in-product generation
- multilingual support
- final admin workflow polish

## Recommended inventory quotas

Use separate quotas by entry type.

### Recommended default quotas
- `30,000` words
- `2,500` phrasal verbs
- `2,000` formulaic expressions
- `1,500` fixed expressions
- `1,000` idioms

Total target: `37,000` entries.

### Rationale
- words remain the backbone of the lexicon,
- phrasal verbs are the highest-value multiword type for learners,
- formulaic expressions are more important for fluency than a large idiom set,
- fixed expressions are useful but easy to bloat,
- idioms should be meaningful but not dominate v1.

## Source strategy

The sourcing problem should be separated from the meaning-generation problem.

### A. Words

Use `wordfreq` as the primary source of common English words.

Role:
- top-30k English single-word inventory
- ranking signal for all single-word entries

Why:
- English-only goal
- stable and practical frequency backbone
- better fit than a one-off web-count CSV

### B. Phrasal verbs

Use a hybrid source stack:
- WordNet / Open English WordNet multiword lemmas
- Kaikki / Wiktextract English entries
- corpus mining rescue pass

Why:
- WordNet alone is incomplete,
- Kaikki/Wiktextract expands coverage,
- corpus mining helps recover common spoken phrasal verbs.

### C. Fixed expressions

Use:
- Kaikki / Wiktextract English entries
- WordNet multiword lemmas where useful
- corpus mining from subtitle/dialogue corpora

Why:
- many fixed expressions are not represented strongly in WordNet,
- corpus evidence helps distinguish useful expressions from low-value combinations.

### D. Idioms

Use:
- Kaikki / Wiktextract English entries
- WordNet multiword lemmas where available
- corpus validation / ranking support

Why:
- idiom coverage from WordNet alone is too weak,
- idioms benefit from lexical candidate sourcing plus usage-frequency filtering.

### E. Formulaic expressions

Use:
- corpus mining first,
- Kaikki / Wiktextract second,
- subtitle/dialogue-heavy sources as the main ranking evidence.

Why:
- formulaic expressions are primarily a usage-frequency phenomenon,
- spoken/conversational data is more valuable than ontology-style lexical coverage.

## Source roles

### `wordfreq`
Use for:
- word inventory selection,
- ranking words,
- ranking/validating candidate multiword entries,
- unified frequency scoring for single and multiword entries.

### WordNet / Open English WordNet
Use for:
- grounded candidate senses,
- lexical context,
- glosses,
- multiword lemma discovery,
- hidden provenance.

Do **not** use as the learner-facing source of truth.

### Kaikki / Wiktextract
Use for:
- candidate entry discovery for multiword expressions,
- phrase/idiom/formulaic-expression coverage,
- optional lexical context for LLM prompts.

Prefer using it as a **candidate-entry source**, not as a direct learner-content source.

### Corpus mining
Use for:
- formulaic-expression discovery,
- fixed-expression ranking,
- phrasal-verb rescue pass,
- filtering obviously low-value multiword candidates.

## Entry processing pipeline

### Step 1. Build candidate inventories

#### Words
- take top `30,000` English words from `wordfreq`
- apply cleanup filters for junk, malformed tokens, and obvious non-entries

#### Multiword candidate pool
Build a combined candidate pool from:
- WordNet/OEWN multiword lemmas
- Kaikki/Wiktextract multiword entries
- corpus-derived candidate n-grams

### Step 2. Normalize and dedupe entries

For each candidate:
- normalize whitespace/case,
- keep a stable `entry_id`,
- store a `normalized_form`,
- dedupe across sources,
- keep provenance of all contributing sources.

### Step 3. Classify entry type

Classify each candidate into one of:
- `word`
- `phrasal_verb`
- `fixed_expression`
- `idiom`
- `formulaic_expression`

Use:
1. deterministic rules first,
2. LLM classification only for ambiguous cases.

The LLM should classify from a bounded label set; it should not invent new types.

### Step 4. Rank within category

Rank entries using:
- `wordfreq` frequency,
- corpus count,
- optional association score for multiword expressions,
- source-confidence heuristics.

Then apply per-category quotas.

## Meaning selection strategy

### Core rule

Do **not** manually select meanings.

The system should:
- gather candidate meaning context from available sources,
- pass bounded grounded context to the LLM,
- ask the LLM to choose the top learner-friendly meanings.

### What the LLM receives

For each entry, provide:
- entry string,
- entry type,
- frequency/rank,
- candidate senses/glosses from WordNet when available,
- lexical context from other sources when available,
- optional corpus usage examples/snippets for multiword expressions.

### What the LLM returns

The LLM should return:
- learner-selected meanings,
- learner-facing definitions,
- learner-facing examples,
- collocations,
- usage notes,
- sense-level synonyms/antonyms,
- domains/register/grammar metadata,
- word-family/morphology fields.

The LLM is choosing the best learner-facing meanings **from source-grounded context**, not from manual sense selection.

## Sense-count policy

Use adaptive caps rather than one flat cap for every entry.

### Words
- rank `<= 3,000`: up to `8`
- rank `3,001–10,000`: up to `6`
- rank `10,001–30,000`: up to `4`

### Phrasal verbs
- up to `4`

### Fixed expressions
- up to `3`

### Formulaic expressions
- up to `3`

### Idioms
- up to `2`

These are maximums, not targets.

## Schema direction

Use schema `1.1.0` as the base, but extend it toward a learner-first entry model.

### Keep
- `schema_version`
- `word`
- `part_of_speech`
- `cefr_level`
- `frequency_rank`
- `forms`
- `senses`
- `confusable_words`
- `generated_at`

### Add / extend
- `entry_id`
- `entry_type`
- `normalized_form`
- `frequency_score`
- `word_family`
- `collocation_summary`
- sense-level `synonyms`
- hidden `provenance`

### Sense-level fields
Sense objects should include:
- `meaning_id` / `sense_id`
- `pos`
- `definition`
- `examples`
- `primary_domain`
- `secondary_domains`
- `register`
- `collocations`
- `grammar_patterns`
- `usage_note`
- `synonyms`
- `antonyms`

Optional hidden provenance fields:
- `wn_synset_id`
- `selection_confidence`
- `generation_confidence`
- `source_context_refs`

## Review policy

Human review should be the exception.

### Auto-accept by default
Auto-accept when:
- entry type is stable,
- source context is coherent,
- LLM output passes validation,
- no major ambiguity signals are triggered.

### Send to review only when necessary
Review only when at least one of these applies:
- highly polysemous high-frequency word,
- multiword entry with unstable type classification,
- strong disagreement across grounded source signals,
- malformed or low-confidence enrichment output,
- repeated rerun instability.

The target should be a small residual review queue rather than review-by-default.

## Operational design

### Main DB should contain only learner-ready entries
Use a clean rule:
- main DB contains validated learner-facing entries,
- unresolved items stay in staging,
- review batches are not the final publication mechanism.

### Final offline flow
1. build candidate inventories
2. normalize/dedupe
3. classify entry type
4. rank and apply quotas
5. collect meaning context from sources
6. LLM selects learner-friendly meanings
7. LLM generates learner-facing enrichment
8. validate
9. import final entries into the local DB
10. stage only the exceptional tail for review

## Success criteria

This design is successful if it gives us:
1. a simpler learner-first mental model,
2. clear entry sources for both words and multiword expressions,
3. LLM-led meaning choice without manual sense selection,
4. very low human-review requirements,
5. a local offline lexicon pipeline that does not depend on online subscriptions.
