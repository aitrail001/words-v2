# 2026-03-24 Real Data Fixture Bootstrap Plan

## Goal

Create a repeatable repo-local fixture and bootstrap path for the current mixed word + phrase lexicon DB so local testing can restore the same learner data after recreating the Docker stack.

## Scope

- Export the current lexicon DB into the same `approved.jsonl` contract used by `tools.lexicon import-db`.
- Store tracked fixtures in-repo for:
  - full real dataset
  - smaller deterministic smoke dataset
- Add a local script path to import either fixture into a recreated Docker stack.
- Preserve row-level provenance where practical so restore behavior matches the current DB closely.
- Run a real-data recreate/import/test pass against Docker and capture resulting issues.

## Design

### Fixture location

Use tracked test fixtures, not `data/`, because `data/` is gitignored:

- `tests/fixtures/lexicon-db/full/approved.jsonl`
- `tests/fixtures/lexicon-db/smoke/approved.jsonl`

### Export contract

Add a lexicon exporter that reads:

- `lexicon.words`
- `lexicon.meanings`
- `lexicon.meaning_examples`
- `lexicon.translations`
- `lexicon.word_relations`
- `lexicon.phrase_entries`

and emits importer-compatible rows:

- word rows with `entry_type=word`, learner metadata, `senses`, translations, examples, and relations
- phrase rows with `entry_type=phrase`, preferably reusing `compiled_payload` when present

### Import fidelity

Extend `import-db` so word rows can honor row-level:

- `language`
- `source_type`
- `source_reference`

This allows exported fixtures to round-trip more faithfully instead of stamping one global source onto all rows.

### Local bootstrap

Add local scripts for:

- exporting current DB to full + smoke fixtures
- importing a chosen fixture into the running Docker stack after migrations

### Verification

- tool tests for exporter serialization and importer provenance handling
- local export from the current populated DB
- Docker stack recreate
- fixture import into empty DB
- smoke/full verification against real data, then capture any product issues surfaced

## Notes

- Full real-data E2E is intended for local/manual validation, not necessarily the default PR smoke path.
- The smoke fixture should stay deterministic and much smaller so local quick checks remain fast.
