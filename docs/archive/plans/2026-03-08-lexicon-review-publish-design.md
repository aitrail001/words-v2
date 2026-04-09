# Lexicon Review Publish Design

**Status:** APPROVED  
**Date:** 2026-03-08  
**Scope:** Publish approved staged lexicon review items into the main `Word` / `Meaning` tables.  
**Live Status Board:** `docs/status/project-status.md`

---

## Goal

Implement `publish-review-batch` as the step after DB-backed review staging and before broader future import evolution.

This publish flow must:

1. publish approved staged lexicon review items into the main learner tables
2. stay idempotent across repeated runs of the same batch
3. support iterative lexicon improvement over time
4. avoid damaging unrelated/manual meanings
5. work with the current simple `Word` / `Meaning` schema even before a richer learner schema lands

---

## Decision Summary

### Chosen approach

Use **replace-by-source** publishing.

### Meaning of replace-by-source

For each approved staged item:

- match or create `Word` by `word + language`
- update `Word` metadata for the current lexicon publish
- delete only meanings for that word whose provenance already belongs to this lexicon publish path
- insert the newly approved meanings in order
- preserve meanings from other sources

### Why this approach

- safer than full meaning-level merge
- more useful than insert-only publishing
- supports repeated lexicon improvements
- works with the current DB schema and provenance fields already present on `Word` and `Meaning`

---

## Alternatives Considered

### Insert-only / skip existing words

**Pros**
- simplest implementation
- lowest overwrite risk

**Cons**
- cannot improve existing words
- cannot correct published lexicon data
- becomes a dead end for iterative publishing

### Meaning-level merge/upsert

**Pros**
- more granular preservation of existing rows

**Cons**
- high complexity without stable meaning identities
- easy to create fuzzy duplicates or partial merges
- unnecessary for the current schema stage

---

## Publish Source Rules

Published rows should use dedicated provenance values:

- `Word.source_type = "lexicon_review_publish"`
- `Word.source_reference = "lexicon_review_batch:<batch_id>"`
- `Meaning.source = "lexicon_review_publish"`
- `Meaning.source_reference = "lexicon_review_batch:<batch_id>:<lexeme_id>:<order_index>"`

These fields make the publish operation auditable and make future replacement of earlier lexicon-published meanings straightforward.

---

## Which Items Publish

Publish only items that are effectively approved.

### Publishable rows

- `review_status = approved`

Because auto-accepted rows are already imported into staging with `review_status = approved`, no separate publish rule is needed for them.

### Non-publishable rows

- `pending`
- `rejected`
- `needs_edit`

If a batch has zero publishable rows, the endpoint should return `400`.

---

## How Meanings Are Built

The current review staging artifact stores ranked candidate metadata and selected synset IDs, but not the full learner-facing compiled export shape.

So this publish slice intentionally projects approved senses into the current simplified meaning schema using staged candidate metadata.

### Meaning field mapping

For each selected synset ID, pick the source metadata row from `candidate_metadata` and write:

- `Meaning.definition` ← `canonical_gloss`
- `Meaning.part_of_speech` ← `part_of_speech`
- `Meaning.example_sentence` ← `NULL`
- `Meaning.order_index` ← publish order

### Selected sense priority

Use the first non-empty source of selected senses:

1. `review_override_wn_synset_ids`
2. `reranked_selected_wn_synset_ids`
3. `deterministic_selected_wn_synset_ids`

If a selected synset ID is missing from `candidate_metadata`, fail the publish request rather than silently publishing incomplete data.

---

## Idempotency

Re-running publish for the same batch should converge.

Mechanism:

- for each affected word, delete existing meanings with `source = lexicon_review_publish`
- reinsert the current approved meanings in deterministic order
- update word provenance to the current batch reference

This prevents duplicate lexicon-published meanings on reruns.

---

## Batch State Changes

On successful publish:

- set `LexiconReviewBatch.status = "published"`
- keep counts in `import_metadata["publish_summary"]`
- set/update `completed_at`

Suggested publish summary fields:

- `published_at`
- `published_word_count`
- `created_word_count`
- `updated_word_count`
- `deleted_meaning_count`
- `created_meaning_count`
- `published_item_count`

---

## API Contract

### Endpoint

- `POST /api/lexicon-reviews/batches/{batch_id}/publish`

### Response

Return a publish summary containing:

- batch id
- batch status
- published item count
- created word count
- updated word count
- deleted meaning count
- created meaning count

### Errors

- `404` when batch is not owned by the current user
- `400` when no items are publishable
- `400` when selected synset IDs cannot be resolved from staged metadata

---

## Testing Strategy

Add focused tests for:

1. successful publish creating or updating `Word` / `Meaning` rows
2. preservation of non-lexicon meanings while replacing lexicon-published meanings
3. `400` when no approved items are publishable
4. `404` for non-owned batch
5. idempotent rerun behavior at the service contract level where practical

---

## Deferred Follow-ups

- richer learner-facing publish from compiled lexicon artifacts instead of candidate glosses only
- publish conflict review / dry-run diff output
- explicit item-level published markers
- incremental import/version governance beyond this batch publish step
