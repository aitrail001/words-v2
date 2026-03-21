# Status: DRAFT
# Lexicon Review Admin Tool Design

Date: 2026-03-21  
Owner: Lexicon/Admin tooling  
Scope: `tools/lexicon`, `backend`, `admin-frontend`, `e2e`, `docs`

## 1. Purpose

Build a production-grade admin review tool for generated lexicon JSONL artifacts so human reviewers can:

- approve generated entries for DB import
- reject generated entries so they are excluded from import
- emit deterministic regeneration requests for the next lexicon run
- review words, phrases/idioms/phrasal verbs, and lightweight learner reference entries with one shared workflow

This tool is a **post-enrichment review gate**. It sits after `compile-export` and before `import-db`.

The current repository already has:

- an offline/admin lexicon pipeline in `tools/lexicon`
- durable JSONL artifacts for normalized snapshots and enrichment runs
- a pre-enrichment review-prep flow for risky sense selection (`score-selection-risk` / `prepare-review` / `review_queue.jsonl`)
- a canonical final DB write path that ends at `import-db`
- dedicated `admin-frontend` and `backend` applications that can host an operator/admin review experience

This design adds a **second review layer for learner-facing compiled entries**.

## 2. Current repo fit

### Existing constraints we should preserve

1. **Do not break the current lexicon pipeline**.
   The repo already treats `build-base -> enrich -> validate -> compile-export -> import-db` as the canonical flow.

2. **Keep generated artifacts immutable**.
   Generated JSONL files should stay replayable and auditable. Human review must be recorded as a separate decision layer, not by mutating model output in place.

3. **Continue using `import-db` as the final publisher into the lexicon schema**.
   The current repo explicitly positions `import-db` as the final writer into `words`, `meanings`, `meaning_examples`, `word_relations`, and enrichment provenance tables.

4. **Follow repo documentation conventions**.
   New planning/design docs should live under `docs/plans/` and use the existing date-based naming convention.

### Key current artifacts and behaviors to build on

From the updated lexicon tool:

- `build-base --output-dir ...` writes durable snapshot files and canonical registry sidecars including `generation_status.jsonl`
- `prepare-review` already stages risky sense selections into `review_queue.jsonl`
- `compile-export` produces learner-facing compiled JSONL rows
- `compile-export --decisions --decision-filter mode_c_safe` already knows how to filter by a decision layer before publishing a compiled export
- `import-db` imports compiled learner-facing JSONL rows into the lexicon DB and stamps source provenance

The review admin tool should feel like a natural extension of this structure.

## 3. Product goals

### Primary goals

- Review one compiled entry at a time with a clean operator UX.
- Support `approve` and `reject` as first-class actions.
- Make approval state auditable and exportable.
- Prevent rejected rows from being imported.
- Produce deterministic regeneration artifacts for rejected rows.
- Work for:
  - words
  - phrases / idioms / phrasal verbs
  - lightweight learner reference entries (names, places, abbreviations, titles, demonyms, etc.)

### Secondary goals

- Pre-seed review priority using deterministic validation and optional QC/LLM judge outputs.
- Allow pagination, search, and filter by learner-relevant metadata.
- Allow future extension to `approve_with_override` and inline edit workflows.

### Non-goals for v1

- Inline editing of compiled content in the UI
- direct model regeneration from the UI
- collaborative simultaneous editing semantics beyond last-write-wins + audit trail
- replacing the existing lexicon CLI import path

## 4. Review granularity

### Decision unit

The review unit should be **one compiled entry row**, not one raw enrichment row.

That means the primary review input is:

- `words.enriched.jsonl`
- later: `phrases.enriched.jsonl`
- later: `references.enriched.jsonl`

### Why compiled-entry review is the right unit

- Reviewers need grouped context: senses, examples, translations, forms, confusables, entity category.
- `import-db` already consumes compiled rows rather than raw per-sense enrichment JSONL.
- Approval should mirror what is about to be published, not a lower-level intermediate representation.

## 5. Core design principle

**Immutable artifact + review overlay**

Generated lexicon artifacts remain immutable. Human review decisions are stored separately and later materialized into:

- `approved.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`
- `review.decisions.jsonl`

This makes the review tool:

- reproducible
- auditable
- safe to rerun
- easy to diff
- compatible with the existing `import-db` flow

## 6. Architecture

## 6.1 High-level components

### A. Offline artifact layer (`tools/lexicon`)

Responsible for:

- generating compiled artifacts
- exporting review candidates
- materializing approved/rejected/regenerate outputs from review decisions
- optionally syncing generation/review status sidecars

### B. Backend review service (`backend`)

Responsible for:

- ingesting review candidate artifacts
- storing searchable review batches/items/decision history
- serving review APIs to `admin-frontend`
- exporting approved/rejected/regenerate artifacts
- optionally triggering operator-safe import handoff later

### C. Admin review UI (`admin-frontend`)

Responsible for:

- queue/list page
- detail page
- approve/reject actions
- filters, counts, and batch progress
- download/export actions for approved/rejected/regenerate artifacts

### D. Existing import path (`tools/lexicon import-db`)

Responsible for:

- importing only approved content
- remaining the canonical final publish step

## 6.2 Recommended end-to-end flow

1. Generate snapshot and enrich as usual.
2. Run `compile-export` as usual.
3. Ingest compiled JSONL into the review service as a **review batch**.
4. Reviewers approve or reject entries in the admin UI.
5. Export:
   - `approved.jsonl`
   - `rejected.jsonl`
   - `regenerate.jsonl`
   - `review.decisions.jsonl`
6. Run `import-db --input approved.jsonl`.
7. Feed `regenerate.jsonl` into the next lexicon run.

## 7. Review data model

The repo already separates lexicon-owned data into the dedicated `lexicon` schema. The new review tables should also live there.

## 7.1 New DB tables

### `lexicon_review_batches`

One row per ingested review artifact.

Suggested fields:

- `id` UUID PK
- `artifact_type` string (`compiled_words`, `compiled_phrases`, `compiled_references`)
- `snapshot_id` string nullable
- `source_type` string nullable
- `source_reference` string nullable
- `artifact_path` text nullable
- `artifact_sha256` string(64) not null
- `compiled_schema_version` string nullable
- `prompt_version` string nullable
- `generator_model` string nullable
- `validator_model` string nullable
- `qc_model` string nullable
- `total_items` integer default 0
- `pending_count` integer default 0
- `approved_count` integer default 0
- `rejected_count` integer default 0
- `status` string (`pending_review`, `review_in_progress`, `review_complete`, `exported`, `imported`)
- `created_by` FK users nullable
- `created_at`
- `updated_at`
- `completed_at` nullable

Indexes:

- `(status)`
- `(snapshot_id)`
- `(artifact_sha256)` unique

### `lexicon_review_items`

One row per compiled entry under review.

Suggested fields:

- `id` UUID PK
- `batch_id` FK -> `lexicon_review_batches`
- `entry_id` string not null
- `entry_type` string not null (`word`, `phrase`, `reference`)
- `display_text` string not null
- `normalized_form` string nullable
- `entity_category` string nullable
- `language` string default `en`
- `frequency_rank` integer nullable
- `cefr_level` string nullable
- `review_status` string not null (`pending`, `approved`, `rejected`)
- `review_priority` integer default 100
- `validator_status` string nullable (`pass`, `warn`, `fail`)
- `validator_issues` JSONB nullable
- `qc_status` string nullable (`pass`, `warn`, `fail`)
- `qc_score` float nullable
- `qc_issues` JSONB nullable
- `compiled_payload` JSONB not null
- `search_text` text nullable
- `reviewed_by` FK users nullable
- `reviewed_at` nullable
- `decision_reason` text nullable
- `regen_requested` boolean default false
- `import_eligible` boolean default false
- `created_at`
- `updated_at`

Indexes:

- `(batch_id, review_status)`
- `(batch_id, entry_type)`
- `(batch_id, entity_category)`
- `(batch_id, frequency_rank)`
- GIN index on `compiled_payload`
- search index on `search_text`

Unique:

- `(batch_id, entry_id)`

### `lexicon_review_item_events`

Immutable audit log.

Suggested fields:

- `id` UUID PK
- `review_item_id` FK -> `lexicon_review_items`
- `event_type` string (`ingested`, `approved`, `rejected`, `reopened`, `exported`, `imported`)
- `actor_user_id` FK users nullable
- `payload` JSONB nullable
- `created_at`

### `lexicon_regeneration_requests`

Derived work queue for future runs.

Suggested fields:

- `id` UUID PK
- `review_batch_id` FK -> `lexicon_review_batches`
- `review_item_id` FK -> `lexicon_review_items`
- `entry_id` string not null
- `entry_type` string not null
- `surface_form` string not null
- `normalized_form` string nullable
- `reject_reason` text nullable
- `requested_by` FK users nullable
- `requested_at`
- `resolved` boolean default false
- `resolved_at` nullable
- `resolution_note` text nullable

## 7.2 Why not store decisions only in JSONL?

Because an admin tool needs:

- pagination
- filters
- reviewer identity
- audit trail
- concurrent operator access
- progress dashboards
- download/export actions

JSONL remains the **export and offline interoperability format**, not the live interaction store.

## 8. File and artifact design

## 8.1 Input artifact

Primary input remains compiled JSONL, one row per reviewable entry.

Example input sources:

- `data/lexicon/snapshots/<snapshot>/words.enriched.jsonl`
- `data/lexicon/snapshots/<snapshot>/phrases.enriched.jsonl`
- `data/lexicon/snapshots/<snapshot>/references.enriched.jsonl`

## 8.2 Exported review artifacts

### `review.decisions.jsonl`

One row per reviewed entry.

Suggested shape:

```json
{
  "review_batch_id": "uuid",
  "entry_id": "...",
  "entry_type": "word",
  "decision": "approved",
  "reviewed_by": "uuid",
  "reviewed_at": "2026-03-21T12:34:56Z",
  "decision_reason": "Meaning set is clean and learner-appropriate.",
  "regen_requested": false,
  "artifact_sha256": "..."
}
```

### `approved.jsonl`

Rows are copied from the original compiled artifact, filtered to approved entries only.

This is the preferred v1 input to `import-db`.

### `rejected.jsonl`

Contains the original compiled payload plus reject metadata for operator analysis.

### `regenerate.jsonl`

Minimal deterministic file for the next run.

Suggested shape:

```json
{
  "entry_id": "...",
  "entry_type": "word",
  "surface_form": "bank",
  "normalized_form": "bank",
  "review_batch_id": "uuid",
  "review_item_id": "uuid",
  "reason": "examples unnatural for ESL learners",
  "prompt_version": "v3",
  "generator_model": "gpt-5-mini",
  "requested_at": "2026-03-21T12:34:56Z"
}
```

## 8.3 Optional sidecar for snapshot status

If the team wants snapshot-local review state, add an optional sidecar:

- `review_status.jsonl`

Suggested fields:

- `snapshot_id`
- `entry_id`
- `review_status`
- `review_batch_id`
- `reviewed_at`
- `import_eligible`
- `regen_requested`

This is optional because the admin DB is the live review source of truth.

## 9. Review state machine

### Allowed states

- `pending`
- `approved`
- `rejected`

### Transitions

- `pending -> approved`
- `pending -> rejected`
- `approved -> pending` (reopen)
- `rejected -> pending` (reopen)

### Derived flags

- `import_eligible = review_status == approved`
- `regen_requested = review_status == rejected`

### v1 policy

- only `approved` rows may be exported to `approved.jsonl`
- all `rejected` rows should be exported to `regenerate.jsonl`
- `pending` rows block the batch from being treated as review-complete

## 10. UI design

## 10.1 Batch list page

Route suggestion:

- `/admin/lexicon/review`

Shows:

- review batches
- artifact type
- snapshot/source reference
- total/pending/approved/rejected counts
- completion percentage
- created at / updated at
- actions: open, export approved, export rejected, export regenerate

## 10.2 Review queue page

Route suggestion:

- `/admin/lexicon/review/:batchId`

Shows:

- filter panel
- paginated table/list of items
- counts by status
- current selection
- keyboard navigation

Recommended filters:

- `review_status`
- `entry_type`
- `entity_category`
- `validator_status`
- `qc_status`
- `frequency_rank`
- `cefr_level`
- search by word / phrase / entry id

Recommended sort options:

- highest review priority first
- highest frequency first
- newest first
- QC failures first

## 10.3 Entry detail panel

For words:

- headword
- pronunciation / forms
- CEFR / POS / frequency / entity category
- senses with examples and translations
- confusable words
- provenance and prompt/model metadata
- validator and QC issues

For phrases/references:

- surface text
- category / type
- brief description
- translations / localized display forms
- pronunciation if available

Actions:

- Approve
- Reject
- Reopen
- optional reviewer note

## 10.4 Reviewer efficiency features

Recommended v1 hotkeys:

- `A` approve
- `R` reject
- `J` next item
- `K` previous item
- `/` focus search

## 11. Backend API design

Exact file paths should follow the backend’s existing router conventions discovered during implementation. If there is already an `/api/admin/...` grouping, use that. Otherwise add a new router under the established API layout.

### Recommended endpoints

#### Batch ingest

- `POST /api/admin/lexicon-review/batches`
  - multipart upload or server-side artifact path reference
  - creates review batch
  - ingests compiled rows into `lexicon_review_items`

#### Batch list/detail

- `GET /api/admin/lexicon-review/batches`
- `GET /api/admin/lexicon-review/batches/{batch_id}`

#### Items

- `GET /api/admin/lexicon-review/batches/{batch_id}/items`
- `GET /api/admin/lexicon-review/items/{item_id}`

#### Decisions

- `POST /api/admin/lexicon-review/items/{item_id}/approve`
- `POST /api/admin/lexicon-review/items/{item_id}/reject`
- `POST /api/admin/lexicon-review/items/{item_id}/reopen`

#### Export

- `POST /api/admin/lexicon-review/batches/{batch_id}/export/approved`
- `POST /api/admin/lexicon-review/batches/{batch_id}/export/rejected`
- `POST /api/admin/lexicon-review/batches/{batch_id}/export/regenerate`
- `POST /api/admin/lexicon-review/batches/{batch_id}/export/decisions`

#### Summary stats

- `GET /api/admin/lexicon-review/batches/{batch_id}/stats`

## 12. Offline/CLI bridge design (`tools/lexicon`)

The admin tool should not replace the CLI; it should complement it.

## 12.1 New CLI command: `review-materialize`

Purpose:

Materialize approved/rejected/regenerate outputs from:

- original compiled input JSONL
- review decision JSONL exported from backend

Suggested command:

```bash
python3 -m tools.lexicon.cli review-materialize \
  --compiled-input data/lexicon/snapshots/demo/words.enriched.jsonl \
  --review-decisions exports/review.decisions.jsonl \
  --approved-output exports/approved.jsonl \
  --rejected-output exports/rejected.jsonl \
  --regenerate-output exports/regenerate.jsonl
```

Behavior:

- validate that all decisions reference existing `entry_id`
- fail loudly on duplicates or mixed artifact hashes
- emit deterministic outputs

## 12.2 Keep `import-db` unchanged in v1

Recommended v1 policy:

- keep `import-db` unchanged
- run `import-db --input approved.jsonl`

This minimizes risk and keeps the current final publisher intact.

### Optional v2

Later add:

- `import-db --review-decisions ... --compiled-input ...`

But do not make this the first implementation.

## 13. Validation and QC integration

The review tool should support both deterministic and model-based pre-screening.

## 13.1 Deterministic validator payload

Each review item may carry:

- schema validation pass/fail
- example count mismatch
- missing translations
- duplicate examples
- overly long fields
- invalid CEFR or POS value
- malformed pronunciation fields

These should be attached as `validator_issues` and surfaced in the UI.

## 13.2 Optional QC judge payload

If a QC pass exists, attach:

- `qc_status`
- `qc_score`
- `qc_issues`

Examples:

- unnatural example sentence
- definition too abstract for learners
- translation mismatch
- culturally narrow / confusing phrasing
- name/place description too thin or too verbose

Human review remains the final authority.

## 14. Approval / rejection policy

### Approval means

- row is learner-appropriate
- row is safe for import
- row may be exported to `approved.jsonl`

### Rejection means

- row must not be imported
- row must be exported to `rejected.jsonl`
- row should normally emit a `regenerate.jsonl` request for future rerun

### Reviewer notes

V1 should store a free-text reason for reject actions. Approval notes are optional.

## 15. Recommended implementation locations

These are target locations; Codex should adapt to the actual repo structure when implementing.

### `tools/lexicon`

Add:

- `tools/lexicon/review_materialize.py`
- CLI wiring in `tools/lexicon/cli.py`
- tests in `tools/lexicon/tests/test_review_materialize.py`

### `backend`

Add:

- review models / migrations under the backend’s existing DB layer
- service module for batch ingest, decision updates, export materialization
- admin API router for review endpoints

### `admin-frontend`

Add:

- lexicon review batch page
- lexicon review item page/panel
- API client hooks/services
- filters, keyboard shortcuts, export actions

### `e2e`

Add:

- admin review flow test
- export approved artifact test
- rejected item excluded from import path test

## 16. Rollout plan

### Phase 1

- build DB-backed review queue
- support approve/reject only
- export approved/rejected/regenerate artifacts
- keep `import-db` unchanged

### Phase 2

- add reviewer notes/search/filters polish
- add batch completion dashboard
- add optional “reopen” flow

### Phase 3

- optional inline overrides
- optional one-click import of approved batch from admin UI
- optional direct regenerate trigger

## 17. Risks and mitigations

### Risk: review system mutates compiled artifacts

Mitigation:

- preserve immutable source artifact
- store decisions separately
- always export materialized outputs as derived artifacts

### Risk: import behavior diverges from reviewed payload

Mitigation:

- use `approved.jsonl` as the sole import input in v1
- stamp artifact hash + batch id onto exports

### Risk: batch/item IDs drift from entry IDs

Mitigation:

- make `entry_id` the stable join key
- validate `entry_id` uniqueness during ingest

### Risk: too much new work in one step

Mitigation:

- keep `import-db` unchanged in v1
- defer inline edit support to later

## 18. Acceptance criteria

1. Admin can ingest a compiled JSONL artifact into a review batch.
2. Admin can approve and reject individual items.
3. Admin UI shows grouped learner-facing content per entry.
4. Exported `approved.jsonl` contains only approved entries.
5. Exported `rejected.jsonl` contains only rejected entries.
6. Exported `regenerate.jsonl` contains deterministic rerun requests for rejected entries.
7. `import-db --input approved.jsonl` succeeds with no codepath regression.
8. Rejected rows are never imported when using the approved export.
9. Full audit trail exists for review actions.
10. Tests cover backend, lexicon CLI materialization, frontend interaction, and end-to-end happy path.

## 19. Open decisions for implementation

1. Exact backend router/module paths should follow the app’s current backend conventions.
2. Exact admin-frontend route/component paths should follow the current admin frontend conventions.
3. Decide whether review batch ingest accepts local file path, upload, or both in v1.
4. Decide whether `review_status.jsonl` is worth adding in phase 1 or deferred to phase 2.

## 20. Recommended first implementation boundary

The safest first slice is:

- ingest compiled JSONL into review DB
- approve/reject in admin UI
- export approved/rejected/regenerate JSONL
- use existing `import-db` on `approved.jsonl`

That gives a real working admin review gate without changing the current importer contract.
