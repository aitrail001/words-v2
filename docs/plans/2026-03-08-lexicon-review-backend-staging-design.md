# Lexicon Review Backend Staging Design

**Status:** APPROVED  
**Date:** 2026-03-08  
**Scope:** Backend staging tables and owner-scoped FastAPI endpoints for importing lexicon review artifacts before final publish/import.  
**Live Status Board:** `docs/status/project-status.md`

---

## Goal

Implement the first backend slice that sits between offline lexicon JSONL generation and any future final import into published `Word` / `Meaning` rows.

This slice must let operators:

1. import `selection_decisions.jsonl` into DB-backed staging storage
2. inspect staged batches and items through the backend
3. mark staged items with review decisions and reviewer comments
4. preserve original row payload and provenance for auditability
5. keep staged review separate from the existing direct `import-db` path

---

## Decision Summary

### Chosen approach

Use dedicated staging tables in the main backend database plus owner-scoped FastAPI endpoints.

### Why this approach

- keeps review state out of published learner-facing tables
- matches existing backend patterns for user-owned resources, auth, and auditing
- supports future admin UI work without forcing humans to inspect raw JSONL
- keeps current `tools/lexicon import-db` behavior separate until publish logic is intentionally added

### What this slice includes

- new backend tables:
  - `lexicon_review_batches`
  - `lexicon_review_items`
- import endpoint for `selection_decisions.jsonl`
- list/detail/items endpoints for staged review batches
- item review-update endpoint
- tests, migration, model exports, router wiring

### What this slice explicitly defers

- publish-to-`Word`/`Meaning` flow
- role-based admin review UI
- incremental diff/publish semantics for final imports
- `review_queue.jsonl` import as a separate required artifact

---

## Data Model

### `lexicon_review_batches`

One row per imported review artifact batch.

Recommended fields:

- `id`
- `user_id`
- `status` (`importing`, `imported`, `reviewing`, `published`, `failed`)
- `source_filename`
- `source_hash`
- `source_type`
- `source_reference`
- `snapshot_id`
- `total_items`
- `review_required_count`
- `auto_accepted_count`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

### `lexicon_review_items`

One row per lexeme decision row from `selection_decisions.jsonl`.

Recommended fields:

- `id`
- `batch_id`
- `lexeme_id`
- `lemma`
- `language`
- `wordfreq_rank`
- `risk_band`
- `selection_risk_score`
- `deterministic_selected_wn_synset_ids`
- `reranked_selected_wn_synset_ids`
- `candidate_metadata`
- `auto_accepted`
- `review_required`
- `review_status` (`pending`, `approved`, `rejected`, `needs_edit`)
- `review_override_wn_synset_ids`
- `review_comment`
- `reviewed_by`
- `reviewed_at`
- `row_payload`
- `created_at`

---

## API Surface

Base router: `/api/lexicon-reviews`

### `POST /batches/import`

Accept a JSONL upload plus optional provenance fields.

Behavior:

- requires auth
- parses and validates every row
- computes hash for idempotency
- returns:
  - `201` for a new imported batch
  - `200` for an already imported identical batch for the same user
  - `202` for a same-hash batch still left in `importing`
- stores both normalized columns and original row payload

### `GET /batches`

Return newest-first list of current user batches.

### `GET /batches/{batch_id}`

Return current-user-owned batch detail and counts.

### `GET /batches/{batch_id}/items`

Return staged items for a batch with optional filters:

- `review_status`
- `risk_band`
- `review_required`

Default ordering:

- `review_required desc`
- `selection_risk_score desc`
- `lemma asc`

### `PATCH /items/{item_id}`

Apply reviewer decisions:

- `review_status`
- optional `review_comment`
- optional `review_override_wn_synset_ids`

Updates reviewer metadata:

- `reviewed_by`
- `reviewed_at`

---

## Security Model

Use the current repo’s lightweight proven pattern:

- every endpoint uses `Depends(get_current_user)`
- every batch and item is owner-scoped by `user_id`
- non-owned or missing resources return `404`
- no new admin-role dependency in this slice

This matches current API behavior and avoids introducing RBAC changes before review staging is functional.

---

## Validation Rules

Minimum required row fields for import:

- `schema_version`
- `snapshot_id`
- `lexeme_id`
- `lemma`
- `language`
- `risk_band`
- `selection_risk_score`
- `deterministic_selected_wn_synset_ids`
- `candidate_metadata`
- `generated_at`
- `generation_run_id`

Additional rules:

- uploaded filename must end in `.jsonl`
- line count and payload size should be bounded conservatively
- malformed JSON or missing required fields returns `400`
- duplicate `lexeme_id` within one file returns `400`

---

## Testing Strategy

Add backend tests for:

- model defaults / relationships / uniqueness-friendly fields
- batch import success
- duplicate import returns existing batch
- malformed file rejected with `400`
- list/detail owner scoping
- item filtering and ordering
- review decision patch updates reviewer metadata
- unauthenticated requests return `401`

---

## Success Criteria

This slice is complete when:

1. an operator can upload `selection_decisions.jsonl` to the backend
2. the backend stores the batch plus item rows in dedicated staging tables
3. the current user can list and inspect staged items
4. the current user can mark review outcomes on staged items
5. tests and migration verification pass
6. live project status is updated with evidence
