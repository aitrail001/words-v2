# Lexicon Review Publish Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `publish-review-batch` so approved staged lexicon review items can be projected into the main `Word` / `Meaning` tables using a source-scoped replace strategy.

**Architecture:** Extend the existing lexicon review backend router with a publish endpoint. Keep the staging tables unchanged if possible. Publish approved staged items by matching or creating `Word` rows, replacing only `Meaning` rows previously published from this lexicon source, and recording publish summary metadata on the batch.

**Tech Stack:** FastAPI, SQLAlchemy ORM, existing auth dependency, current `Word` / `Meaning` models, pytest.

---

## Task 1 — Confirm publish inputs and provenance rules

1. Re-read `backend/app/api/lexicon_reviews.py`, `backend/app/models/word.py`, `backend/app/models/meaning.py`, and `tools/lexicon/import_db.py`.
2. Keep the publish source constants consistent across `Word` and `Meaning` updates.
3. Use candidate metadata glosses for this slice; do not block on richer learner export integration.

## Task 2 — Write failing publish tests first

1. Add focused tests for `POST /api/lexicon-reviews/batches/{batch_id}/publish`.
2. Cover:
   - successful publish to `Word` / `Meaning`
   - replace-by-source behavior preserving non-lexicon meanings
   - `400` when no items are approved
   - `404` for non-owned batch
3. Run the publish-focused tests and confirm they fail for the missing endpoint/logic reasons.

## Task 3 — Add publish response schema and helpers

1. Extend `backend/app/api/lexicon_reviews.py` with a publish response model.
2. Add helper functions for:
   - selecting publishable item senses
   - mapping selected synsets back to staged candidate metadata
   - source reference generation
   - source-scoped meaning replacement

## Task 4 — Implement publish endpoint

1. Add `POST /api/lexicon-reviews/batches/{batch_id}/publish`.
2. Enforce owner scoping through the existing batch lookup helper.
3. Load approved items for the batch.
4. Fail with `400` if there are no publishable items.
5. For each item:
   - find/create `Word`
   - update word provenance/metadata
   - delete old `Meaning` rows with `source = lexicon_review_publish`
   - insert new meanings from approved selected synsets in order
6. Update batch status and `import_metadata.publish_summary`.
7. Commit once per publish request.

## Task 5 — Verify and adjust

1. Run the publish-focused backend tests.
2. Run the broader lexicon review backend test set.
3. Run `py_compile` for touched backend files.
4. Fix only publish-slice issues revealed by those runs.

## Task 6 — Update live status

1. Add a new row to `docs/status/project-status.md`.
2. Record the exact publish verification evidence.
3. Note that richer learner-field publishing remains deferred.
