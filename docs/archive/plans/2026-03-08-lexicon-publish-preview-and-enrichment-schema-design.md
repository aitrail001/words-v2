# Lexicon Publish Preview and Enrichment Schema Design

**Status:** APPROVED  
**Date:** 2026-03-08  
**Scope:** Add a publish dry-run / diff preview for staged lexicon review batches, then implement the first learner-facing enrichment schema slice aligned with `SCHEMA_REFERENCE.md`.  
**Live Status Board:** `docs/status/project-status.md`

---

## Goal

Advance the lexicon publish pipeline in two ways:

1. add a safe preview mode so admins can inspect publish impact before mutating `Word` / `Meaning`
2. evolve the backend schema toward the richer learner-facing enrichment model that belongs to the LLM enrichment layer

---

## Decision Summary

### 1. Publish dry-run / diff preview

Add a read-only preview endpoint for staged review batches.

Recommended route:

- `GET /api/lexicon-reviews/batches/{batch_id}/publish-preview`

This route should compute the same replace-by-source publish plan as the real publish endpoint, but without writing to the database.

### 2. Learner-facing enrichment schema evolution

Implement a first schema slice that matches the existing prototype reference instead of inventing a new parallel model.

For now, implement:

- word phonetic enrichment provenance fields on `Word`
- `meaning_examples`
- `word_relations`
- `lexicon_enrichment_jobs`
- `lexicon_enrichment_runs`

Defer for now:

- `meaning_phrases`
- concept graph tables
- phrase enrichment flow
- full admin/API enrichment workflow

---

## Why this split

### Preview first

The current staged review backend can publish approved items, but it still benefits from a safer operator workflow.

A preview route gives:

- no-write inspection
- counts before publish
- per-word impact visibility
- better future admin UI foundations

### Schema evolution separately

The richer learner-facing fields are part of the LLM enrichment layer, not the sense-selection staging layer.

So the right long-term architecture is:

- selection/review decides **which senses** publish
- enrichment stores **learner-facing content** for those senses
- publish combines both

---

## Publish Preview Design

### Output

Return aggregate counts plus per-item summaries.

Aggregate fields:

- `batch_id`
- `publishable_item_count`
- `created_word_count`
- `updated_word_count`
- `replaced_meaning_count`
- `created_meaning_count`
- `skipped_item_count`

Per-item fields:

- `item_id`
- `lemma`
- `language`
- `action` (`create_word`, `update_word`, `skip`)
- `selected_synset_ids`
- `existing_lexicon_meaning_count`
- `new_meaning_count`
- `warnings`

### Rules

- preview only `review_status = approved`
- no DB mutation
- fail with `400` when no approved items are publishable
- use the same sense-resolution logic as real publish

### Goal of reuse

The preview and publish paths should share a common planning function so the real publish is just “apply this plan”.

---

## Learner-Facing Enrichment Schema Slice

### Why these tables

These tables are already defined in `SCHEMA_REFERENCE.md` and fit the LLM enrichment layer:

- `meaning_examples`
- `word_relations`
- `lexicon_enrichment_jobs`
- `lexicon_enrichment_runs`

Also add the phonetic enrichment provenance fields to `words`:

- `phonetic_source`
- `phonetic_confidence`
- `phonetic_enrichment_run_id`

### Why not use `meanings` for everything

The learner-facing layer is broader than a single definition row. It includes:

- examples
n- relations
- enrichment provenance
- confidence
- model/provider tracking

Keeping that in dedicated enrichment tables is cleaner than overloading `meanings`.

### What this slice does not yet do

- no enrichment API endpoints yet
- no background enrichment pipeline yet
- no automatic publish-from-enrichment join yet
- no examples/relations on the public word detail API yet

This is a schema-first step so later enrichment work has a proper home.

---

## Testing Strategy

### Preview tests

Add API tests for:

- preview success on approved items
- preview `400` when no items are publishable
- preview `404` for non-owned batch
- preview reports create vs update counts and replacement counts

### Schema tests

Add model tests for:

- defaults and unique constraints on enrichment tables
- word phonetic provenance fields present
- basic relationship wiring where practical

### Verification

Use the same containerized Python 3.11 backend verification path already used for lexicon review backend tests.

---

## Success Criteria

This combined slice is complete when:

1. admins can preview publish impact without mutating the DB
2. preview uses the same planning logic as publish
3. the backend schema now includes the first learner-facing enrichment tables/provenance fields
4. focused tests and broader staged-review backend tests pass
5. live project status documents the results and remaining deferred work
