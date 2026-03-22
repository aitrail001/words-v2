# Lexicon Admin Inspector Browse Design

**Date:** 2026-03-22

## Goal

Streamline the lexicon admin portal by making path guidance consistent across review/import pages, upgrading DB Inspector from search-only to browse-plus-inspect for `word`, `phrase`, and `reference` entries, and adding a safe batch-delete operation for compiled review staging data.

## Problems In The Current UI

1. Path help is duplicated and inconsistent across `Compiled Review`, `JSONL Review`, and `Import DB`.
2. `DB Inspector` assumes the operator already knows a word to search for, which is too weak for final verification after import.
3. `Compiled Review` review DB batches accumulate with no admin cleanup path, which makes review staging harder to operate over time.

## Non-Goals

1. No change to the final lexicon import contract.
2. No attempt to merge DB-backed and JSONL-only review storage models.
3. No broad review workflow redesign beyond the affected pages.

## Recommended Approach

### 1. Shared Path Guidance Component

Create one reusable admin UI component for path help and use it on:

- `Compiled Review`
- `JSONL Review`
- `Import DB`

The shared guidance should define one canonical vocabulary:

- compiled artifact:
  - `data/lexicon/snapshots/<snapshot>/words.enriched.jsonl`
- reviewed directory:
  - `data/lexicon/snapshots/<snapshot>/reviewed/`
- approved import input:
  - `data/lexicon/snapshots/<snapshot>/reviewed/approved.jsonl`
- decision ledger:
  - `data/lexicon/snapshots/<snapshot>/reviewed/review.decisions.jsonl`
- Docker-visible equivalent:
  - `/app/data/...`

Each page adds a short mode-specific note:

- `Compiled Review`: decisions live in review DB until export/materialize
- `JSONL Review`: decisions are file-backed
- `Import DB`: prefer `reviewed/approved.jsonl`

This removes drift and gives operators one mental model.

### 2. Unified DB Inspector Browse Flow

Keep one route, `/lexicon/db-inspector`, but change it to a real browseable inspector.

#### Backend

Add a new browse endpoint for final lexicon entries with:

- `family=all|word|phrase|reference`
- `q`
- `limit`
- `offset`
- `sort`

Use a flat summary row contract for the result list so the UI can render mixed families consistently.

Example summary fields:

- `id`
- `family`
- `display_text`
- `normalized_form`
- `source_reference`
- `cefr_level`
- `frequency_rank`
- `updated_at`

Keep detail fetches family-aware:

- `word` detail can continue using the existing word detail endpoint
- add equivalent detail endpoints or a unified detail endpoint for `phrase` and `reference`

#### Frontend

Use the current two-pane inspector shell:

- left pane:
  - search box
  - family filter
  - sort control
  - paginated/browseable result list
- right pane:
  - selected entry detail

This keeps search, but removes the requirement that operators already know what to look up.

### 3. Compiled Review Batch Deletion

Add a reviewed-staging cleanup action for compiled review batches.

#### Behavior

- Allow deleting an entire compiled-review batch from the review DB.
- Require explicit confirmation in the UI.
- Delete associated review items and review item events with the batch.
- If regeneration requests are tied to those items/batches, delete or cascade them consistently.

#### Constraints

- This should delete only review staging data, not final lexicon DB rows.
- The API should reject unknown batch IDs with `404`.
- The UI should refresh the batch list and clear the detail panel if the selected batch is deleted.

This is an admin maintenance tool, not part of the happy-path workflow.

## Data/API Design

### Shared Path Guidance

No backend change required.

### DB Inspector Browse API

Recommended REST shape:

- `GET /api/lexicon-inspector/entries?family=all&q=bank&sort=updated_desc&limit=25&offset=0`
- `GET /api/lexicon-inspector/entries/{family}/{id}`

This keeps browse and detail contracts separate and makes pagination explicit.

### Batch Delete API

Recommended REST shape:

- `DELETE /api/lexicon-compiled-reviews/batches/{batch_id}`

Response:

- `204 No Content` on success

## UI Flow

### Shared Path Help

All three pages show the same path reference block near the top, with only a one-line page-specific note changing.

### DB Inspector

1. Open inspector
2. Browse all entries by default
3. Narrow with search/family/sort
4. Select one result
5. Inspect final DB detail

### Compiled Review Batch Delete

1. Select batch
2. Click `Delete Batch`
3. Confirm
4. Batch disappears from the list
5. Detail panel resets to the next available batch or empty state

## Testing Strategy

### Backend

- browse endpoint pagination/filter tests
- mixed-family result coverage
- batch delete success and not-found tests

### Frontend

- shared path guidance rendering tests
- DB Inspector browse/filter/pagination tests
- compiled review batch delete tests

### E2E

- browse imported DB entries in inspector
- delete a compiled review batch and verify it disappears

## Risks

1. Mixed-family browse queries can become awkward if the backend tries to fully unify unlike ORM models in one query.
   - Mitigation: use a simple summary projection layer, even if the implementation performs family-specific queries then merges.

2. Batch deletion could accidentally remove more than review staging data.
   - Mitigation: keep deletion logic scoped strictly to review tables and test it explicitly.

3. Shared path guidance can still drift if copy is duplicated.
   - Mitigation: extract one component and one source of truth.

## Recommendation

Implement this as one admin UX slice:

1. shared path guidance component
2. browseable multi-family DB Inspector
3. compiled review batch deletion

That keeps the operator model coherent and removes two current friction points without changing the underlying lexicon artifact pipeline.
