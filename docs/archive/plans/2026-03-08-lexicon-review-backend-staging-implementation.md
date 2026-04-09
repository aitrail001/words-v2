# Lexicon Review Backend Staging Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add backend staging tables and owner-scoped APIs for importing and reviewing `selection_decisions.jsonl` before any final publish/import to the main word tables.

**Architecture:** Keep lexicon generation in `tools/lexicon/`. Add a backend staging layer with one batch table and one item table, then expose import/list/detail/review APIs under a dedicated FastAPI router.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, Pydantic, existing JWT auth dependency, pytest.

---

## Task 1 — Document approved design

1. Verify the approved design doc exists at `docs/plans/2026-03-08-lexicon-review-backend-staging-design.md`.
2. Re-read `backend/app/models/__init__.py`, `backend/app/main.py`, and one recent Alembic revision to confirm integration anchors.
3. Keep scope limited to staging import/review only; do not add publish logic in this slice.

## Task 2 — Write failing backend tests first

1. Add API tests in `backend/tests/test_lexicon_reviews_api.py` for:
   - successful batch import
   - duplicate import returning existing batch
   - invalid filename / malformed JSONL / missing required fields returning `400`
   - unauthenticated requests returning `401`
   - batch detail `404` for non-owned batch
   - items filter behavior
   - patching item review decision
2. Add model tests in `backend/tests/test_lexicon_review_models.py` for defaults / relationships where practical.
3. Run only the new tests and confirm they fail for the expected missing-feature reasons.

## Task 3 — Add staging ORM models

1. Create `backend/app/models/lexicon_review_batch.py`.
2. Create `backend/app/models/lexicon_review_item.py`.
3. Follow existing UUID/timestamp/default patterns already used in backend models.
4. Add relationships between batch and items plus reviewer linkage to `User`.
5. Export the new models in `backend/app/models/__init__.py`.

## Task 4 — Add Alembic migration

1. Create a new Alembic revision after `006_add_lexicon_import_provenance.py`.
2. Add `lexicon_review_batches` table with indexes and unique `(user_id, source_hash)`.
3. Add `lexicon_review_items` table with indexes and unique `(batch_id, lexeme_id)`.
4. Add appropriate foreign keys and downgrade cleanup in reverse order.

## Task 5 — Implement review-staging API router

1. Create `backend/app/api/lexicon_reviews.py`.
2. Add router-local Pydantic request/response schemas.
3. Implement JSONL parsing/validation helpers for the import route.
4. Implement:
   - `POST /api/lexicon-reviews/batches/import`
   - `GET /api/lexicon-reviews/batches`
   - `GET /api/lexicon-reviews/batches/{batch_id}`
   - `GET /api/lexicon-reviews/batches/{batch_id}/items`
   - `PATCH /api/lexicon-reviews/items/{item_id}`
5. Enforce owner scoping with `get_current_user` and `404` for non-owned resources.

## Task 6 — Wire router and keep API surface coherent

1. Register the new router in `backend/app/main.py`.
2. Keep naming and response semantics consistent with existing backend APIs.
3. Avoid adding publish endpoints or frontend-specific concerns.

## Task 7 — Make tests pass

1. Run the new lexicon review API/model tests.
2. Implement the smallest necessary fixes until they pass.
3. Run adjacent backend tests if needed to confirm no regression in auth/import patterns.

## Task 8 — Update docs and live status

1. Update `docs/status/project-status.md` with the implemented backend staging slice and fresh evidence.
2. Mention that publish-to-main tables remains deferred.

## Task 9 — Verify before claiming completion

1. Run targeted backend tests for the new slice.
2. Run a broader backend test subset if the changed modules touch shared auth/router behavior.
3. Run `py_compile` or equivalent for the modified backend Python files.
4. Report exactly what passed and what remains deferred.
