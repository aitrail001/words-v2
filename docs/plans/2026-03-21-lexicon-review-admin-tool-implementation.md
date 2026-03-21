# Lexicon Review Admin Tool Implementation

Date: 2026-03-21
Status: Implemented in feature worktree

## Scope

Add a separate admin review tool for compiled lexicon JSONL artifacts so review can happen before DB import without reusing the older selection-review domain.

## Delivered

1. Backend persistence and API
   - Added `lexicon_artifact_review_batches`
   - Added `lexicon_artifact_review_items`
   - Added `lexicon_artifact_review_item_events`
   - Added `lexicon_regeneration_requests`
   - Added Alembic migration `012_add_compiled_review_tables.py`
   - Added admin API router at `/api/lexicon-compiled-reviews`
   - Supported batch import, batch/item listing, item decision updates, and export endpoints for approved/rejected/regenerate/decisions

2. Lexicon CLI bridge
   - Added `review-materialize`
   - Validates compiled rows and canonical decision overlays
   - Produces approved/rejected/regenerate JSONL outputs from review decisions

3. Admin frontend
   - Added `/lexicon/compiled-review`
   - Supports batch import, item inspection, approve/reject/reopen, filter/search, and artifact export
   - Added nav entry to the admin shell

4. Verification
   - Added backend model/API tests
   - Added lexicon CLI tests
   - Added admin frontend tests
   - Verified backend/frontend compile/lint/build for changed scope

## Intentional Boundaries

1. This does not replace the older selection-review flow.
2. Review decisions remain an overlay on immutable compiled artifacts.
3. This slice does not add compiled-review Playwright smoke yet.
4. This slice does not add final operator-runbook coverage beyond status/docs updates.

## Follow-ups

1. Add end-to-end smoke for import -> review -> export.
2. Expand operator docs around the compiled-review workflow.
3. Decide whether to add richer server-side pagination/filtering if artifact sizes grow beyond current admin-page expectations.
