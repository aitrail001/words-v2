# Admin Lexicon Portal Split Design

**Status:** APPROVED

**Date:** 2026-03-16

## Goal

Reshape the admin lexicon area around the workflow that is actually in use now:
- inspect offline snapshot progress
- inspect imported DB words in full detail
- keep staged review available only as a legacy path

The admin portal should stop presenting staged `selection_decisions.jsonl` review as a primary operator flow when the current real 30K snapshot path does not produce those artifacts.

## Current Reality

The current admin IA mixes three separate concerns:

1. staged review and publish of `selection_decisions.jsonl`
2. inspection of imported `Word` rows already persisted in the DB
3. inspection of offline snapshot folders and pipeline artifacts

This causes two practical problems:

1. the “Imported word inspector” is buried inside the staged-review page even though it is useful independently
2. the primary `/lexicon` page over-emphasizes staged review, even though the current real 30K snapshots in:
   - `data/lexicon/snapshots/words-30000-20260314-main-real-entity-tail-hardened`
   - `data/lexicon/snapshots/words-30000-20260316-main-real-enrich-live`
   do not contain `selection_decisions.jsonl`

## Design Decision

Split the admin lexicon portal into three separate surfaces with different priority levels:

1. **Lexicon Words**: first-class page for inspecting imported DB words
2. **Lexicon Operations**: first-class page for inspecting snapshot folders and artifact progress
3. **Legacy Review**: retained, but clearly marked as a legacy/staged-review tool

The root `/lexicon` route should become a small section landing page that points operators to the current primary surfaces and separately calls out the legacy review tool.

## Recommended Routes

- `/lexicon`
  - section landing page
  - cards/links for `Words`, `Operations`, and `Legacy Review`
- `/lexicon/words`
  - dedicated DB inspector
- `/lexicon/ops`
  - existing snapshot monitor, retained and clarified
- `/lexicon/review`
  - moved legacy staged-review page

## Information Architecture

### 1. Lexicon Words

Purpose:
- search imported words already persisted in the DB
- inspect the full stored schema, not just a subset of learner-facing enrichment

This page should show:

- word-level fields
  - `id`
  - `word`
  - `language`
  - `phonetic`
  - `phonetic_source`
  - `phonetic_confidence`
  - `phonetic_enrichment_run_id`
  - `cefr_level`
  - `learner_part_of_speech`
  - `confusable_words`
  - `learner_generated_at`
  - `frequency_rank`
  - `word_forms`
  - `source_type`
  - `source_reference`
  - `created_at`

- meaning-level fields
  - `id`
  - `definition`
  - `part_of_speech`
  - `wn_synset_id`
  - `primary_domain`
  - `secondary_domains`
  - `register_label`
  - `grammar_patterns`
  - `usage_note`
  - `learner_generated_at`
  - `example_sentence`
  - `order_index`
  - `source`
  - `source_reference`
  - `created_at`

- child data
  - `translations`
  - `meaning_examples`
  - `word_relations`
  - referenced `lexicon_enrichment_runs`

The page should distinguish:
- learner-facing content
- provenance and generation metadata
- raw JSON-structured fields

### 2. Lexicon Operations

Purpose:
- inspect snapshot folders and artifact progress for the real offline pipeline

This remains a first-class page because it aligns with the active operator workflow. It should continue to surface:
- snapshot identity
- stage status
- artifact counts
- tracked file presence
- freshness / update timestamps

The copy should make the role explicit:
- this page reflects offline snapshot and artifact state
- this page is not the same thing as DB inspection

### 3. Legacy Review

Purpose:
- preserve the existing staged review flow for `selection_decisions.jsonl` import, review, and publish

This page should be retained because the backend, frontend, and CLI still support it. However, it should be framed as:
- optional
- legacy
- not part of the main 30K operator path

The page copy should state that current real snapshot flows may not produce `selection_decisions.jsonl`, and that this tool is only relevant when the optional review-prep path is used.

## Backend Contract Changes

The existing `/api/words/{word_id}/enrichment` response is too narrow for a true DB inspector.

Expand it to include missing persisted fields:

- word-level:
  - `word_forms`
  - `source_type`
  - `source_reference`
  - `created_at`

- meaning-level:
  - `register_label` should remain mapped to frontend-friendly `register`
  - `source`
  - `source_reference`
  - `created_at`
  - `translations`

The existing endpoint can remain in place and be expanded rather than replaced.

## UI Design Notes

### `/lexicon`

Use a lightweight landing page with three cards:
- `Words` as the main inspection tool for imported DB content
- `Operations` as the main inspection tool for snapshot pipeline state
- `Legacy Review` as a secondary/legacy tool

### `/lexicon/words`

Structure:
- search panel
- selected word summary
- word record section
- meanings section
- nested translations/examples/relations per meaning
- enrichment provenance section

Rendering rules:
- scalar fields should be visible without opening raw JSON
- JSON fields should be rendered readably and still preserve exact values
- empty fields should be shown explicitly as absent rather than disappearing silently

### `/lexicon/review`

Keep the current functionality but add clear “legacy” framing:
- title and description
- possible helper note linking operators toward `/lexicon/words` and `/lexicon/ops`

## Alternatives Considered

### Option 1: Keep current tabs and only relabel them

Pros:
- smallest code change

Cons:
- preserves the current conceptual mixing
- keeps DB inspection secondary
- still over-emphasizes staged review

### Option 2: Remove staged review entirely

Pros:
- simpler admin IA

Cons:
- removes a still-supported capability
- risks losing a useful fallback/diagnostic path

### Option 3: Split into current-vs-legacy surfaces

Pros:
- aligns admin IA with real operator behavior
- preserves legacy tooling safely
- minimal backend churn

Cons:
- requires route reshaping and UI moves

This is the selected option.

## Testing Strategy

- backend API tests for expanded word-detail response
- admin frontend tests for:
  - `/lexicon` landing page
  - `/lexicon/words`
  - `/lexicon/review` legacy framing
  - updated nav
- regression coverage for `/lexicon/ops`

## Success Criteria

- operators can inspect all persisted word fields from the admin UI
- snapshot monitoring remains first-class
- staged review is still available but no longer presented as the main path
- the admin IA matches the actual real 30K workflow in use today
