# Lexicon Enrichment Import Writeback Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evolve the offline lexicon compiled schema and importer so enriched output persists learner-facing examples, supported relations, and enrichment provenance into the local DB.

**Architecture:** Keep the existing offline pipeline and extend the compiled JSONL contract just enough for importer writeback. `compile-export` remains the boundary between enrichment generation and DB import. `import-db` becomes responsible for stable upsert/replace-by-scope writes into `words`, `meanings`, `meaning_examples`, `word_relations`, `lexicon_enrichment_jobs`, and `lexicon_enrichment_runs`.

**Tech Stack:** Python CLI tooling, dataclass-based lexicon models, SQLAlchemy ORM models in backend, unittest/pytest, Docker-based Python 3.11 verification.

---

## Task 1 — Re-read importer and compiled contract

1. Re-read `tools/lexicon/models.py`, `tools/lexicon/compile_export.py`, `tools/lexicon/import_db.py`, and current importer tests.
2. Keep scope tight to examples, supported relations, and enrichment provenance.
3. Do not add public backend APIs in this slice.

## Task 2 — Write failing tests first

1. Extend lexicon tool tests for compiled export to assert the new sense-level provenance fields are preserved.
2. Extend importer tests to assert creation/update behavior for:
   - enrichment job
   - enrichment run
   - meaning examples
   - supported word relations
3. Verify the new tests fail for the expected missing-behavior reasons.

## Task 3 — Evolve compiled word schema

1. Update the compiled sense payload to include:
   - `enrichment_id`
   - `generation_run_id`
   - `model_name`
   - `prompt_version`
   - `confidence`
   - `generated_at`
2. Keep backward compatibility where practical for existing consumer paths.

## Task 4 — Implement importer writeback

1. Keep current word/meaning upsert behavior intact.
2. Add importer helpers to resolve backend enrichment models lazily.
3. Create/reuse one `LexiconEnrichmentJob` per word for `phase1`.
4. Create or update one `LexiconEnrichmentRun` per imported sense.
5. Replace imported `meaning_examples` for each meaning from compiled examples.
6. Replace supported imported `word_relations` for each meaning using:
   - synonyms -> `synonym`
   - antonyms -> `antonym`
   - confusable words -> `confusable`
7. Leave collocations and other future learner-facing fields deferred.

## Task 5 — Verify importer stability

1. Run focused lexicon tool tests for compile/import paths.
2. Run broader lexicon tool tests if focused tests pass.
3. Run `py_compile` on touched lexicon tooling files.
4. If backend model imports are involved, run targeted Docker/backend verification only as needed.

## Task 6 — Update live status

1. Add a new row to `docs/status/project-status.md`.
2. Record verification evidence.
3. Note which learner-facing fields remain intentionally deferred.
