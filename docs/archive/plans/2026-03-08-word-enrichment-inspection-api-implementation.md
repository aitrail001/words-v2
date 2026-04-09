# Word Enrichment Inspection API Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only backend endpoint for inspecting imported learner-facing enrichment attached to a word.

**Architecture:** Extend the existing `words` API with a dedicated enrichment inspection route that assembles data from `words`, `meanings`, `meaning_examples`, `word_relations`, and `lexicon_enrichment_runs` into a stable admin/operator response without altering the existing word detail contract.

**Tech Stack:** FastAPI, Pydantic response models, SQLAlchemy async sessions, pytest with mocked DB sessions, Docker verification if needed.

---

## Task 1 — Re-read words API and tests

1. Re-read `backend/app/api/words.py` and `backend/tests/test_words.py`.
2. Keep the slice read-only and separate from the current word detail route.
3. Follow existing auth and 404 patterns.

## Task 2 — Write failing tests first

1. Add focused tests for `GET /api/words/{word_id}/enrichment` covering:
   - successful response with examples, relations, and runs
   - 404 when the word does not exist
   - auth required
2. Verify the new tests fail for the missing route/logic reasons.

## Task 3 — Implement response models and route

1. Add response models for examples, relations, enrichment runs, and enriched meanings.
2. Implement `GET /api/words/{word_id}/enrichment` in `backend/app/api/words.py`.
3. Keep query logic explicit and easy to verify.
4. Do not mutate the DB.

## Task 4 — Verify focused backend coverage

1. Run focused `backend/tests/test_words.py`.
2. Run `py_compile` on touched backend files.
3. If needed, run broader backend Docker verification for the changed scope.

## Task 5 — Update live status

1. Add a new row to `docs/status/project-status.md`.
2. Record exact verification evidence.
3. Note that role-based admin gating remains a later hardening slice.
