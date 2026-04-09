# Phrase Enrichment Design

**Date:** 2026-03-22
**Status:** Approved for planning, not yet implemented
**Owner:** Engineering

---

## Goal

Add phrasal verbs and idioms as first-class lexicon phrase entries using curated CSV inventories, then run them through the same enrichment, review, and import lifecycle already used for word entries.

The immediate source inventories are:

- `data/lexicon/phrasals/reviewed_phrasal_verbs.csv`
- `data/lexicon/idioms/reviewed_idioms.csv`

This design keeps phrase storage separate from `words`, but aligns phrase artifacts with the existing lexicon tooling and admin portal so phrases can be reviewed and imported in the same interfaces.

---

## Problem

The current word inventory/build flow depends on single-word sources such as Wordfreq and WordNet-backed selection. Those sources do not provide adequate coverage for multiword expressions such as phrasal verbs, idioms, fixed expressions, formulas, and similar phrase-level entries.

The repository already contains:

- phrase snapshot support in `tools/lexicon/phrase_pipeline.py`
- phrase compiled export support in `tools/lexicon/compile_export.py`
- phrase DB import support in `tools/lexicon/import_db.py`
- a `PhraseEntry` model in `backend/app/models/phrase_entry.py`
- a phrase structured-output schema starter in `tools/lexicon/schemas/phrase_enrichment_schema.py`

However, the current phrase path is thin:

- there is no equivalent of `build-base` for curated phrase inventories
- phrase enrichment is not wired into the existing runtime the way word enrichment is
- the DB model only stores lightweight phrase metadata, not full learner-facing enriched payloads

---

## Design Summary

### Decisions

1. Treat the reviewed CSVs as phrase inventory sources, equivalent to word build inputs.
2. Keep phrases as `entry_type="phrase"` rather than forcing them into the `words` table.
3. Align phrase enrichment to the existing word enrichment runtime and admin workflow.
4. Support both realtime and batch execution modes on the same phrase contract.
5. Keep minimal v1 taxonomy small, while preserving raw reviewed labels for future upgrades.
6. Store rich phrase payload on `phrase_entries` in v1 rather than creating a parallel relational phrase-meaning schema immediately.

### Non-Goals

- No attempt to store multiword phrases as normal word rows.
- No separate phrase-only admin portal.
- No expanded phrase subtype taxonomy in v1 beyond what is needed for stable enrichment.
- No phrase-specific learner UI redesign in this slice.

---

## Source Inventory Model

Phrase build should accept one or more CSV inventory files and normalize them into snapshot rows written to `phrases.jsonl`.

Each input row currently exposes:

- `expression`
- `original_order`
- `source`
- `reviewed_as`
- `difficulty`
- `commonality`
- `added`
- `confidence`

### Canonical phrase snapshot row

Each normalized row written to `phrases.jsonl` should include:

- `snapshot_id`
- `entry_kind="phrase"`
- `entry_type="phrase"`
- `entry_id`
- `normalized_form`
- `display_form`
- `phrase_kind`
- `language`
- `source_provenance`
- `seed_metadata`
- `created_at`

### Phrase identity

- `normalized_form` is the canonical dedupe key
- `entry_id` should be derived deterministically from normalized form
- repeated entries across multiple CSVs should merge provenance rather than duplicate rows

### Source provenance

`source_provenance` should remain a list so a phrase can trace back to multiple inventory sources later. Each source row should preserve:

- source file path or stable source label
- original order
- raw reviewed label
- raw difficulty
- raw commonality
- raw confidence
- `added` flag

### Seed metadata

`seed_metadata` should contain the normalized summary used for prioritization and later operator inspection, for example:

- `raw_reviewed_as`
- `commonality`
- `difficulty`
- `review_confidence`
- `added`
- `source_order`

---

## Minimal V1 Phrase Taxonomy

The input CSVs contain more phrase subtypes than the current enrichment contract can cleanly support. For v1, map them into the existing small set of phrase kinds.

### Internal mapping

- `phrasal verb` -> `phrasal_verb`
- `prepositional verb` -> `phrasal_verb`
- `phrasal-prepositional verb` -> `phrasal_verb`
- `multi-word verb` -> `phrasal_verb`
- `idiom` -> `idiom`
- all other reviewed labels -> `multiword_expression`

### Raw label preservation

The original `reviewed_as` value must be retained in provenance/seed metadata so future schema upgrades can split:

- formula/discourse
- proverb/saying
- simile
- sentence frame/pattern
- fixed/prepositional phrase
- binomial phrase

without re-reviewing the source inventories.

---

## Enrichment Contract

Phrase enrichment should reuse the same strict structured-output architecture used for words:

- one input item per enrichment task
- strict JSON schema response
- response normalization and validation
- accepted artifact materialization
- failure sidecars / regenerate flow
- realtime and batch parity

The phrase contract should remain parallel to word artifacts, but with phrase semantics.

### Phrase enrichment input

The LLM input for a phrase row should include:

- `entry_type`
- `display_form`
- `normalized_form`
- `phrase_kind`
- `language`
- `seed_metadata`
- `source_provenance`

### Phrase enrichment output

The compiled output should remain close to word compiled rows:

- `schema_version`
- `entry_id`
- `entry_type="phrase"`
- `normalized_form`
- `source_provenance`
- `entity_category`
- `word`
- `display_form`
- `phrase_kind`
- `part_of_speech`
- `cefr_level`
- `frequency_rank`
- `forms`
- `senses`
- `confusable_words`
- `generated_at`
- `confidence`
- `seed_metadata`

### Sense structure

For v1, phrase rows should use `senses[]`, not a single top-level definition, to stay parallel to word enrichment and to fit the admin review and compiled artifact model.

Each phrase sense should contain:

- `sense_id`
- `definition`
- `part_of_speech`
- `examples`
- `grammar_patterns`
- `usage_note`
- `translations`
- optional `synonyms`
- optional `antonyms`
- optional `collocations`

### Bounds

To keep phrase outputs stable and reviewable:

- default to 1-2 senses per phrase
- require at least 1 example per sense
- use the same translation locales as word enrichment
- avoid word-style morphology assumptions

### Prompt guidance

The phrase prompt should follow the same operator/runtime structure as the word prompt, but instruct the model to:

- define the phrase, not its component words independently
- prefer common learner-relevant senses
- use the exact phrase naturally in examples
- avoid literal-only interpretations for idiomatic phrases unless genuinely common
- supply grammar patterns appropriate to multiword usage

---

## Runtime Modes

Phrase enrichment should support both runtime modes on one contract:

### Realtime

- first implementation target
- direct per-phrase enrich path
- best for prompt tuning and small curated inventories

### Batch

- later implementation phase
- same phrase prompt/schema/materialization contract
- only transport and request/ingest mechanics differ

The same accepted/review/regenerate artifact flow should apply to both modes.

---

## Compiled Artifact And Admin Alignment

Phrase rows must pass through the existing lexicon admin workflow rather than introducing a separate phrase review system.

### Required alignment

- compile phrase outputs into `phrases.enriched.jsonl`
- materialize phrase review decisions into the existing reviewed artifact layout
- allow compiled review and JSONL review to render `entry_type="phrase"`
- use the same approve/reject/reopen/regenerate decision system
- import approved phrase rows through the current Import DB interface
- inspect imported phrase rows through the current DB inspector path

### Practical constraint

The phrase compiled shape must stay intentionally parallel to the word compiled shape so the admin portal can branch on `entry_type` rather than requiring a new review subsystem.

---

## DB Model

Phrase storage should remain separate from words.

### V1 recommendation

Extend `backend/app/models/phrase_entry.py` rather than building a new relational phrase-meaning schema immediately.

Minimal additions:

- `compiled_payload` JSON
- `seed_metadata` JSON
- `confidence_score`
- `generated_at`

Keep current searchable/display fields:

- `phrase_text`
- `normalized_form`
- `phrase_kind`
- `language`
- `cefr_level`
- `register_label`
- `brief_usage_note`
- provenance fields

### Why this is the right v1 tradeoff

- keeps implementation small
- preserves full learner-facing phrase payload
- supports idempotent re-import by normalized form
- keeps later migration open if phrase volume or lookup needs justify deeper normalization

---

## Lookup And Product Surface

Storage stays separate, but lookup should eventually be unified.

Desired end state:

- exact phrase queries match phrase rows first
- phrase entries can be returned alongside word entries
- phrase data remains stored in phrase-specific DB records underneath

This design document does not require implementing unified learner lookup immediately, but the phrase import and compiled shape should be designed so that later API integration is straightforward.

---

## Risks

### Taxonomy compression risk

Mapping many reviewed labels into `idiom` / `multiword_expression` / `phrasal_verb` loses some presentation nuance.

Mitigation:

- preserve raw reviewed labels in metadata
- keep v1 enums small
- expand later only when learner/admin surfaces need explicit subtype handling

### Over-generation risk

Phrase enrichment may invent obscure or literal senses.

Mitigation:

- bound sense count
- keep strict schema
- ensure admin review renders phrase-specific fields clearly
- use the existing regenerate flow for low-quality outputs

### Storage rigidity risk

If `PhraseEntry` remains too thin, import will lose learner payload.

Mitigation:

- add `compiled_payload` and related metadata in v1
- keep raw compiled artifact accessible for later migrations

---

## Verification Expectations For Implementation

Implementation should verify at minimum:

- phrase inventory build tests
- phrase schema and normalization tests
- realtime phrase enrichment tests
- compile/export tests for phrase outputs
- review materialization tests with phrase rows
- import-db tests persisting rich phrase payload
- backend/admin tests showing phrase rows in existing review/import interfaces

---

## Decision

Approved direction:

- build phrase inventory from curated CSVs
- enrich phrases using a phrase-specific strict schema with `senses[]`
- support realtime first and batch second on the same contract
- keep phrase storage separate from words
- align compiled artifacts and admin workflow with the existing lexicon review/import system
