# 2026-03-12 — Lexicon one-run-per-word import and stage-100 verification

## Scope

Fix DB provenance so compiled per-word enrichment imports create one enrichment run row per word request instead of one row per meaning, then wipe the local DB and verify a fresh real 100-word run into the repo data folder.

## Design

1. Group imported senses by shared `generation_run_id` / model / prompt version.
2. Create or reuse one `lexicon_enrichment_run` per run-group instead of per sense.
3. Keep meaning/example/relation rows attached to the grouped run id.
4. Reset the local DB while preserving schema.
5. Run `build-base -> enrich -> validate -> compile-export -> import-db` for the 100-word rollout into `data/lexicon/snapshots/words-100-20260312-fresh`.
6. Verify total counts and sampled words in Postgres.
