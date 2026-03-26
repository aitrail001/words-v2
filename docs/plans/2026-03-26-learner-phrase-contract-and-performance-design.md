# Learner Phrase Contract and Performance Design

**Date:** 2026-03-26

## Problem

The learner knowledge-map and detail surfaces currently serve words and phrases through different runtime contracts.

- Words are read primarily from normalized lexicon tables.
- Phrases are read primarily from `lexicon.phrase_entries.compiled_payload`.
- The frontend contains fallback logic that behaves differently depending on entry type and payload shape.
- Phrase/example translations can disappear between approved artifacts and imported learner data.
- Range loads and individual detail loads show high CPU on backend/Postgres/frontend, which is consistent with JSON-heavy hot-path reads and heterogeneous rendering logic.

Observed symptoms in scope:

- learner range loads trigger high backend and Postgres CPU
- individual word/phrase loads trigger high frontend CPU
- phrase-only list views can show localized translation without English definition
- mixed list views can show English without localized translation
- phrase detail can show `"Translation unavailable"`
- `approved.jsonl` test artifacts can lose example-sentence translations
- `phrase_entries` and related tables rely on too many JSON columns for learner-serving paths

Out of scope for this slice:

- changing learner UX to show two examples instead of one
- broader lexicon admin workflow changes
- unrelated review/publish flows

## Goals

1. Serve words and phrases through one canonical learner contract.
2. Always expose both English definition and localized translation when available.
3. Remove hot learner-serving dependence on wide phrase JSON payloads.
4. Preserve phrase example translations through export/import boundaries.
5. Reduce CPU cost for range loads and individual detail loads.

## Non-Goals

1. Redesign learner card layouts beyond the minimum needed for contract consistency.
2. Expand example-count presentation from one to two.
3. Remove every JSON column in the lexicon schema; this slice only removes JSON from hot learner-serving paths.

## Recommended Approach

Normalize phrases onto the same persisted learner shape as words for hot-path serving.

- Keep provenance JSON only where it still has operator/debug value.
- Stop using `phrase_entries.compiled_payload` as the primary learner read source.
- Persist phrase senses, localized definitions, usage notes, examples, and example translations in structured storage.
- Update knowledge-map APIs to return the same semantic fields for both entry types.
- Update the importer so approved/compiled artifacts populate the normalized phrase learner data directly.

This is preferred over a caching-only approach because the current issues are contract drift plus runtime cost, not just missing memoization.

## Architecture

### 1. Canonical learner read model

The learner API should treat `word` and `phrase` entries as different sources of the same read model:

- `english_definition`
- `localized_definition`
- localized usage note
- examples with optional localized translation
- metadata needed for list and detail surfaces

Words may continue using the existing normalized tables. Phrases should be migrated so the learner-facing subset is no longer extracted repeatedly from `compiled_payload`.

### 2. Phrase storage normalization

Add structured phrase learner storage parallel to the existing word meaning/example/translation shape. The exact schema can be tuned during implementation, but the data model needs first-class rows/columns for:

- phrase sense identity/order
- English definition
- localized definition by locale
- usage notes/register/domains/grammar patterns
- examples
- example translations by locale
- related term buckets needed by learner detail views

`phrase_entries.compiled_payload` may remain as archival provenance during transition, but not as the normal serving path for list/detail endpoints.

Phrase metadata that is currently learner-visible must also become normalized per sense rather than remaining only in `compiled_payload`. In practice, that means the normalized phrase-sense storage must cover:

- `part_of_speech`
- `register`
- `primary_domain`
- `secondary_domains`
- `grammar_patterns`
- `synonyms`
- `antonyms`
- `collocations`

Heuristic read-time matching back to `compiled_payload` is not sufficient once QC/manual overrides or repeated imports can reorder, merge, rewrite, or drop senses.

### 3. API contract cleanup

Knowledge-map range/list/detail endpoints should stop encoding entry-type-specific display rules.

Canonical rules:

- list items always include English definition
- list items always include localized translation when available
- detail payloads always use the same field semantics for examples and localized text
- missing localized content is represented as `null`, not synthetic strings such as `"Translation unavailable"`

### 4. Import/export boundary hardening

The lexicon pipeline must preserve phrase example translations through:

- approved artifact generation
- compiled export
- DB import

Importer validation should fail loudly when required phrase/example translation fields are missing or discarded.

## Performance Strategy

### Backend

- return a thin projection for range/list endpoints
- avoid hydrating detail-only fields for range/list requests
- stop repeated JSON traversal for phrase summaries
- share one shaping path for word/phrase summaries to reduce conditional branching and repeated fallback work

### Postgres

- move learner-hot phrase fields to structured tables/columns
- query indexed structured fields instead of scanning/extracting wide JSON payloads
- keep provenance JSON off the hot path

### Frontend

- consume one normalized contract for both words and phrases
- remove entry-type-driven fallback rendering where possible
- reduce state churn on detail/overlay loads
- memoize expensive derived rendering only around the active sense/meaning and overlay target

## Error Handling

- missing localized translations are data gaps, not runtime errors
- API returns `null` for absent localized fields
- UI decides fallback presentation without inventing backend error strings
- import/export validation errors should surface at pipeline boundaries, not at learner render time

## Testing Strategy

### Backend API regression coverage

Add or update tests for:

- word-only ranges
- phrase-only ranges
- mixed ranges
- phrase detail from normalized learner data rather than `compiled_payload`
- null localized fields instead of `"Translation unavailable"`

### Import/export regression coverage

Add or update tests for:

- phrase example translation preservation in approved/compiled artifacts
- importer persistence of phrase examples and localized translations
- failure paths when required phrase/example translation fields are missing

### Frontend regression coverage

Add or update tests for:

- list cards showing both English and localized translation for words and phrases
- detail rendering using the unified contract
- reduced entry-type-specific fallback behavior

## Acceptance Criteria

1. Loading a learner range no longer exhibits the current backend/Postgres CPU spike pattern.
2. Loading an individual word/phrase no longer exhibits the current frontend CPU spike pattern.
3. Word-only, phrase-only, and mixed list views all show English definition plus localized translation consistently.
4. Phrase detail no longer emits `"Translation unavailable"` for a missing translation; it uses `null` and UI fallback behavior.
5. Phrase example translations survive approved artifact generation, export, and import.
6. Hot learner-serving phrase reads no longer depend primarily on `phrase_entries.compiled_payload`.

## Risks

1. Phrase schema migration can touch importer, API, and tests at once; keep the write path and read path tightly scoped.
2. Existing admin/operator tooling may still inspect `compiled_payload`; preserve provenance compatibility while shifting learner reads away from it.
3. Mixed read/write transition risk is high if both normalized phrase data and `compiled_payload` remain partially authoritative; implementation should define one source of truth for learner-serving fields before flipping API reads.

## Deferred Follow-Up

1. Decide whether learner detail should show two examples instead of one.
2. Revisit remaining JSON-heavy lexicon tables not exercised by learner hot paths.
3. Add stronger query/perf instrumentation once the contract cleanup lands.
