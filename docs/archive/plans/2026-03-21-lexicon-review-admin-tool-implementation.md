# Lexicon Review Admin Tool Implementation

Date: 2026-03-21
Status: Implemented in feature worktree

## Scope

Add a separate admin review tool for compiled lexicon JSONL artifacts so review can happen before DB import without reusing the older selection-review domain.

Chosen implementation note:

- This branch ships the DB-backed staged-review path.
- The lighter file-backed alternative is documented in `docs/plans/2026-03-21-lexicon-review-admin-tool-jsonl-only-design.md`.
- Follow-up approved for this task: implement that JSONL-only mode later as a separate route and separate backend API without changing the DB-backed compiled-review implementation.

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

5. JSONL-only follow-up
   - Added separate admin API router at `/api/lexicon-jsonl-reviews`
   - Keeps review state in `review.decisions.jsonl` sidecars instead of review DB tables
   - Reuses `review-materialize` for approved/rejected/regenerate outputs
   - Added separate admin route at `/lexicon/jsonl-review`
   - Added focused backend/frontend tests plus Playwright smoke for the file-backed flow
   - Re-verified the DB-backed compiled-review smoke beside the new JSONL-only smoke

## Intentional Boundaries

1. This does not replace the older selection-review flow.
2. Review decisions remain an overlay on immutable compiled artifacts.
3. This slice does not replace the DB-backed compiled-review path.
4. This slice does not add final operator-runbook coverage beyond status/docs updates.

## Follow-ups

1. Expand operator docs around when to use DB-backed compiled review versus JSONL-only review.
2. Decide whether JSONL-only review needs snapshot browsing or stronger server-side pagination for larger artifacts.
3. Add broader mixed-surface admin smoke only if the current focused smoke pair stops being sufficient.
