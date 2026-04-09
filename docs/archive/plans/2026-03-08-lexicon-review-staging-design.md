# Lexicon Review Staging Design

**Status:** APPROVED  
**Date:** 2026-03-08  
**Scope:** Offline/admin lexicon selection-risk scoring, bounded rerank routing, staging review storage, future admin review UI, and publish-to-local-DB workflow for lexicon snapshots.  
**Live Status Board:** `docs/status/project-status.md`

---

## Goal

Define how the lexicon tool should move from offline JSONL generation into a scalable human-review workflow without forcing reviewers to inspect raw JSONL files.

The design must support:

1. deterministic selection as the primary production backbone
2. optional bounded LLM rerank for high-risk words only
3. automatic acceptance for low-risk rerank outputs
4. targeted human review for a small flagged subset
5. full provenance visibility for WordNet candidates, deterministic ranking, rerank output, and reviewer decisions
6. future admin UI integration without blocking current lexicon-tool progress

---

## Decision Summary

### Chosen approach

Use the existing project backend/admin architecture as the future home for lexicon review, but keep review data in a separate staging layer before publish.

### Core decisions

- keep lexicon generation as a separate offline/admin tool under `tools/lexicon/`
- do not ask humans to review raw `jsonl` files directly
- do not publish directly from lexicon snapshots into learner-facing `Word` / `Meaning` rows
- introduce a staging review layer in the local database for selection decisions and reviewer actions
- auto-apply bounded rerank only to high-risk words
- auto-accept many rerank outcomes using explicit rules
- reserve human review for a much smaller flagged queue
- treat a future admin UI as planned follow-up work because `admin-frontend/` is not implemented in the current worktree

### Future UI status

The review UI is part of the planned workflow, but it is explicitly TODO for a later slice. The current repo snapshot does not contain `admin-frontend/`, so this design documents the target behavior and data contracts first.

---

## Existing Integration Anchors

The future review system should align with current repo patterns rather than inventing a separate stack. Useful integration anchors in the current codebase are:

### Backend patterns to reuse later

- import-job lifecycle model: `backend/app/models/import_job.py`
- import submit/list/detail APIs: `backend/app/api/word_lists.py`
- job status/event streaming pattern: `backend/app/api/import_jobs.py`
- router composition: `backend/app/main.py`
- published-word provenance fields: `backend/app/models/word.py`, `backend/app/models/meaning.py`
- provenance migration precedent: `backend/alembic/versions/006_add_lexicon_import_provenance.py`

### Lexicon-tool anchors to extend

- current DB import path: `tools/lexicon/import_db.py`
- current CLI surface: `tools/lexicon/cli.py`
- operator docs: `tools/lexicon/README.md`, `tools/lexicon/OPERATOR_GUIDE.md`

### Product/planning anchors

- planned admin/content curation direction: `docs/plans/2026-02-26-full-rebuild.md`
- schema/planned curation reference: `SCHEMA_REFERENCE.md`
- canonical live project state: `docs/status/project-status.md`

---

## Why this approach

### Why not review JSONL directly

Raw JSONL review becomes painful as soon as the corpus grows:

- poor filtering and triage
- no reviewer assignment or status tracking
- no side-by-side deterministic vs rerank diffing
- no comments/tags history
- no audit-friendly approval workflow
- hard to expose original WordNet candidate context cleanly

JSONL remains useful as a machine artifact, not as the main human-review surface.

### Why not a separate standalone review app first

A dedicated review DB + mini app would work technically, but it duplicates:

- authentication
n- admin permissions
- audit patterns
- backend APIs
- operational deployment

Given the existing backend/admin direction in this repo, the simpler long-term path is to reuse the main stack while isolating review data in staging tables or a review schema.

### Why same DB instance but separate staging tables

Recommended operational default:

- same Postgres instance
- separate `lexicon_review_*` tables or a separate `lexicon_review` schema
- separate publish step into learner-facing tables

This gives:

- lower integration cost
- better auditability
- easier local development
- less risk of corrupting published learner data during repeated lexicon experiments

---

## Operating Model

### Lane A — deterministic only

Use deterministic selection only for most words.

This is the default path for:

- low-polysemy words
- clean WordNet neighborhoods
- words with a strong score margin at the deterministic cutoff

### Lane B — deterministic + bounded `candidates` rerank + auto-accept

Use `candidates` rerank automatically for high-risk words, then auto-accept when the output passes groundedness and stability rules.

This is the recommended quality-improvement path.

### Lane C — rerank + human review

Use human review only for a smaller flagged queue, not for every reranked word.

This queue is built from:

- high-risk words with large deterministic/rerank disagreement
- suspicious rerank substitutions
- high-frequency words with unstable outputs
- words that introduce noisy or specialized replacement senses

---

## Where rerank helps most

The bounded `candidates` rerank mode is expected to help most on:

- highly polysemous words
- messy WordNet neighborhoods
- close-call selector cutoffs
- words with multiple plausible POS families
- words with specialized/legal/sports/religious/geometry tails near the boundary

The benchmark evidence on 2026-03-08 supports this pattern. `candidates` improved several difficult lemmas without needing full manual review, while `full_wordnet` was noticeably noisier.

---

## Proposed Staging Data Model

These are design-level target entities for the future backend review layer.

### `LexiconReviewBatch`

Purpose: one imported offline review batch.

Recommended fields:

- `id`
- `snapshot_id`
- `source_reference`
- `source_type`
- `created_at`
- `imported_at`
- `created_by`
- `status` (`imported`, `in_review`, `ready_to_publish`, `published`, `archived`)
- `lexeme_count`
- `needs_review_count`
- `auto_accepted_count`
- `approved_count`
- `published_count`

### `LexiconReviewLexeme`

Purpose: one reviewable lexeme/headword decision record.

Recommended fields:

- `id`
- `batch_id`
- `lexeme_id`
- `lemma`
- `language`
- `wordfreq_rank`
- `available_wordnet_sense_count`
- `deterministic_target_count`
- `selection_risk_score`
- `selection_risk_reasons` (JSON array)
- `rerank_applied`
- `rerank_candidate_source`
- `rerank_candidate_count`
- `replacement_count`
- `auto_accepted`
- `review_required`
- `status` (`pending`, `auto_accepted`, `needs_review`, `approved`, `rejected`, `published`)
- `reviewer_id` nullable
- `reviewed_at` nullable
- `published_at` nullable

### `LexiconReviewCandidateSense`

Purpose: preserve original WordNet candidate context and ranking metadata.

Recommended fields:

- `id`
- `review_lexeme_id`
- `wn_synset_id`
- `part_of_speech`
- `canonical_label`
- `canonical_gloss`
- `lemma_count`
- `query_lemma`
- `deterministic_score`
- `deterministic_rank`
- `rerank_exposed` boolean
- `deterministic_selected` boolean
- `rerank_selected` boolean
- `final_selected` boolean
- `candidate_flags` JSON array
- `source_mode` nullable (`selected_only`, `candidates`, `full_wordnet`)

### `LexiconReviewDecision`

Purpose: preserve deterministic, rerank, and final approved sense sets.

Recommended fields:

- `id`
- `review_lexeme_id`
- `deterministic_selected_wn_synset_ids` JSON array
- `reranked_selected_wn_synset_ids` JSON array nullable
- `final_selected_wn_synset_ids` JSON array nullable
- `accepted_strategy` (`deterministic`, `rerank`, `manual`)
- `replacement_count`
- `auto_accept_reasons` JSON array
- `review_reasons` JSON array
- `publish_ready` boolean

### `LexiconReviewComment`

Purpose: reviewer notes, rationale, and future selector-learning feedback.

Recommended fields:

- `id`
- `review_lexeme_id`
- `author_id`
- `comment_type` (`note`, `issue`, `approval_note`, `selector_feedback`)
- `body`
- `tags` JSON array
- `created_at`

### `LexiconReviewActionLog`

Purpose: audit trail for review and publish operations.

Recommended fields:

- `id`
- `review_lexeme_id`
- `actor_id`
- `action`
- `payload` JSON
- `created_at`

---

## Future Admin UI

### Status

TODO for a later slice.

### Why deferred

The current worktree does not contain `admin-frontend/`, so the review interface should not block lexicon-tool progress now. The data model and offline artifacts should be designed first so UI work later has a stable contract.

### Required UI views

When admin UI work starts, the first useful version should include:

1. **Batch list**
   - list review batches
   - show counts and status
   - open a batch or publish approved rows

2. **Review queue**
   - filter flagged words only
   - sort by risk score, frequency, replacement count, batch, reviewer, status
   - search by lemma / synset / tag

3. **Lexeme detail page**
   - show lemma metadata
   - show all original WordNet candidates
   - show deterministic ranking and chosen senses
   - show rerank output and diff
   - allow final grounded selection approval
   - capture comments and tags

4. **Diff view**
   - deterministic vs rerank vs final approved set
   - highlight added, dropped, reordered senses

5. **Candidate explorer**
   - sortable WordNet candidates with gloss, POS, score, flags, and selection states

### Reviewer actions

The UI should support:

- approve deterministic selection
- approve rerank selection
- manually choose final senses from grounded candidates only
- mark `needs custom entry`
- add comments and tags
- assign reviewer
- publish approved decisions later

---

## Publish Workflow

The future publish path should be separate from staging import.

### Recommended flow

1. lexicon tool generates normalized snapshot + decision artifacts
2. import review artifacts into staging tables
3. auto-accept low-risk outputs
4. reviewers handle the flagged queue
5. publish approved lexeme/sense decisions into learner-facing tables
6. keep staging records and audit history for future tuning

### Why separate publish matters

This preserves:

- repeatable reruns
- safe rollback
- review history
- tuning evidence for deterministic/rerank logic
- ability to revisit old decisions without mutating learner data prematurely

---

## Non-Goals For This Slice

This design does not implement yet:

- the admin frontend screens
- backend review APIs
- DB migrations for review staging tables
- auto-publish into production learner tables
- idiom/custom-expression review UI

Those belong in later implementation slices.

---

## Acceptance Criteria For The Next Implementation Slice

The next implementation spec should cover:

1. exact `selection_decisions.jsonl` schema
2. exact selection-risk formula and thresholds
3. CLI steps to score risk and prepare a review batch
4. import path from offline artifacts into staging review storage
5. future backend/API touchpoints for review and publish
6. explicit TODO marker for admin UI work until the admin app exists
