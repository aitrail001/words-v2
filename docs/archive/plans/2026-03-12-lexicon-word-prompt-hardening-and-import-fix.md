# 2026-03-12 — Lexicon word prompt hardening and import fix

## Scope

Tighten the per-word enrichment prompt so OpenAI-compatible models are less likely to exceed learner meaning caps, add a single repair retry for invalid word-level payloads, and fix local DB import replacement behavior discovered during a live smoke.

## Design

1. Keep the per-word enrichment contract grounded in existing WordNet candidate senses only.
2. Strengthen prompt language to repeat the hard cap and require a JSON object only.
3. Retry once with a repair prompt when the first word-level payload is invalid.
4. Flush deleted examples/relations before re-inserting replacements during import to avoid unique-constraint collisions on re-import.
5. Verify with focused tests, full lexicon tests, and one real `run set play` smoke through `build-base -> enrich -> validate -> compile-export -> import-db`.

## Evidence

- Focused tests: `tools/lexicon/tests/test_enrich.py` and `tools/lexicon/tests/test_import_db.py`
- Full lexicon suite: `tools/lexicon/tests`
- Backend config regression: `backend/tests/test_config.py`
- Real smoke artifacts: `/tmp/lexicon-per-word-real-20260312-set-repair`
