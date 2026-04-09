# Lexicon Publish Preview and Enrichment Schema Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dry-run publish preview for staged lexicon review batches and implement the first learner-facing enrichment schema slice aligned with `SCHEMA_REFERENCE.md`.

**Architecture:** Refactor the current lexicon publish route so publish planning is reusable by both preview and real publish. In parallel, add the first enrichment-domain backend tables and word-level provenance fields so later LLM enrichment can persist learner-facing examples, relations, and run metadata without overloading `meanings`.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, pytest, existing JWT auth dependency, Docker-based Python 3.11 verification.

---

## Task 1 — Capture approved design

1. Verify the design doc exists at `docs/plans/2026-03-08-lexicon-publish-preview-and-enrichment-schema-design.md`.
2. Re-read `backend/app/api/lexicon_reviews.py`, `backend/app/models/word.py`, `SCHEMA_REFERENCE.md`, and the current publish tests.
3. Keep scope limited to preview plus schema evolution; do not add public word-detail enrichment APIs yet.

## Task 2 — Write failing preview tests first

1. Add/extend backend tests for `GET /api/lexicon-reviews/batches/{batch_id}/publish-preview`.
2. Cover:
   - successful preview summary
   - `400` when no approved items are publishable
   - `404` for non-owned batch
3. Run the focused preview tests and confirm they fail for the missing route/logic reasons.

## Task 3 — Refactor publish planning helpers

1. Extract reusable helpers in `backend/app/api/lexicon_reviews.py` for:
   - resolving selected publish senses
   - mapping candidate metadata into publishable meanings
   - computing create/update/replace actions per item
2. Implement the preview route using those helpers with no DB mutation.
3. Keep the actual publish route using the same planning logic.

## Task 4 — Write failing schema tests first

1. Add model tests for the new enrichment schema tables and word provenance fields.
2. Cover defaults/constraints for:
   - `MeaningExample`
   - `WordRelation`
   - `LexiconEnrichmentJob`
   - `LexiconEnrichmentRun`
3. Verify the tests fail for missing models/fields before implementation.

## Task 5 — Implement enrichment schema models

1. Modify `backend/app/models/word.py` to add:
   - `phonetic_source`
   - `phonetic_confidence`
   - `phonetic_enrichment_run_id`
2. Create:
   - `backend/app/models/meaning_example.py`
   - `backend/app/models/word_relation.py`
   - `backend/app/models/lexicon_enrichment_job.py`
   - `backend/app/models/lexicon_enrichment_run.py`
3. Export them in `backend/app/models/__init__.py`.

## Task 6 — Add Alembic migration

1. Create a new revision after `007_add_lexicon_review_staging.py`.
2. Add the new word columns.
3. Create the enrichment tables with indexes, unique constraints, and foreign keys matching `SCHEMA_REFERENCE.md` as closely as practical within the current repo.
4. Add downgrade cleanup in reverse order.

## Task 7 — Verify preview and schema together

1. Run focused preview tests.
2. Run the broader staged-review backend suite including the publish tests.
3. Run the new schema model tests.
4. Run `py_compile` on touched backend files.
5. Use the Python 3.11 Docker test path for authoritative verification.

## Task 8 — Update live status

1. Add a new row to `docs/status/project-status.md`.
2. Record preview and schema verification evidence.
3. Note that richer API/pipeline usage of the enrichment tables remains a later slice.
