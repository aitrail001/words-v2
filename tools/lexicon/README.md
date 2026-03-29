# Lexicon Tool

Offline/admin lexicon pipeline for building word and phrase snapshots, generating learner-facing enrichments, reviewing them, importing approved rows into the DB, and generating/importing derived voice assets from reviewed rows.

## Current contract

The active pipeline is lexeme-first for words, with curated phrase inventory support on the same compiled/review/import contract:

1. `build-base`
2. optional `build-phrases`
3. optional ambiguous-form adjudication
4. `enrich`
5. `validate`
6. human review of `words.enriched.jsonl`
7. `import-db` from reviewed `approved.jsonl`
8. optional `voice-generate` from reviewed `approved.jsonl`
9. optional `voice-import-db` from `voice_manifest.jsonl`

Realtime enrichment writes final compiled word and phrase rows directly to `words.enriched.jsonl`.
Batch enrichment can still use intermediate request/result ledgers, but accepted word and phrase rows are materialized into the same `words.enriched.jsonl` contract.

Legacy sense-selection and staged-selection review flows are removed from the supported operator surface.

## Main commands

- `.venv-lexicon/bin/python -m tools.lexicon.cli build-base ...`
  - builds a normalized lexeme snapshot
  - writes `lexemes.jsonl` plus canonicalization/operator sidecars
- `.venv-lexicon/bin/python -m tools.lexicon.cli detect-ambiguous-forms ...`
  - emits only unresolved canonicalization tails
- `.venv-lexicon/bin/python -m tools.lexicon.cli adjudicate-forms ...`
  - resolves bounded ambiguous-form tails
- `.venv-lexicon/bin/python -m tools.lexicon.cli build-phrases ...`
  - builds curated phrase inventory rows from one or more reviewed CSVs
  - writes `phrases.jsonl`
- `.venv-lexicon/bin/python -m tools.lexicon.cli enrich --snapshot-dir ...`
  - realtime per-entry enrichment
  - reads `lexemes.jsonl` and optional `phrases.jsonl`
  - writes `words.enriched.jsonl`
  - keeps `enrich.checkpoint.jsonl`, `enrich.decisions.jsonl`, `enrich.failures.jsonl`
- `.venv-lexicon/bin/python -m tools.lexicon.cli validate --snapshot-dir ...`
  - validates snapshot inputs and outputs
- `.venv-lexicon/bin/python -m tools.lexicon.cli validate --compiled-input ...`
  - validates compiled learner-facing JSONL rows
- `.venv-lexicon/bin/python -m tools.lexicon.cli batch-prepare --snapshot-dir ...`
  - writes batch request ledgers
- `.venv-lexicon/bin/python -m tools.lexicon.cli batch-ingest --snapshot-dir ...`
  - ingests completed batch output JSONL
  - writes accepted rows to `words.enriched.jsonl`
  - writes failed rows to `words.regenerate.jsonl`
- `.venv-lexicon/bin/python -m tools.lexicon.cli import-db --input ...`
  - dry-runs or imports reviewed learner-facing rows into the DB
- `.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input ... --output-dir ...`
  - generates deterministic voice artifacts and JSONL ledgers from reviewed `approved.jsonl`
  - supports reviewed word rows and reviewed phrase rows in the same input
  - writes `voice_plan.jsonl`, `voice_manifest.jsonl`, and `voice_errors.jsonl`
  - prints startup, planning, progress, failure, and completion summaries during long runs
  - `--locales` currently expects a comma-separated value such as `en-US,en-GB`
- `.venv-lexicon/bin/python -m tools.lexicon.cli voice-import-db --input ...`
  - imports generated voice manifest rows into normalized DB voice-asset tables
- `.venv-lexicon/bin/python -m tools.lexicon.cli voice-sync-storage --source-reference ... --storage-kind ... --storage-base ... [--fallback-storage-kind ... --fallback-storage-base ...]`
  - re-points matching storage policies to a primary and optional fallback storage target after files are copied to cloud/object storage

## Snapshot artifacts

Core snapshot files now used by the active pipeline:

- `lexemes.jsonl`
- optional `phrases.jsonl`
- `canonical_entries.jsonl`
- `canonical_variants.jsonl`
- `generation_status.jsonl`
- `ambiguous_forms.jsonl`
- optional `form_adjudications.jsonl`
- realtime outputs:
  - `words.enriched.jsonl`
  - `enrich.checkpoint.jsonl`
  - `enrich.decisions.jsonl`
  - `enrich.failures.jsonl`
- batch outputs:
  - `batch_requests.jsonl`
  - `batch_jobs.jsonl`
  - `batch_results.jsonl`
  - `words.regenerate.jsonl`
- reviewed outputs:
  - `reviewed/approved.jsonl`
  - `reviewed/rejected.jsonl`
  - `reviewed/regenerate.jsonl`
  - `reviewed/review.decisions.jsonl`
- voice outputs:
  - `voice_plan.jsonl`
  - `voice_manifest.jsonl`
  - `voice_errors.jsonl`
  - provider/family/locale-organized audio files under the selected voice output directory

The active pipeline no longer relies on `senses.jsonl`, `concepts.jsonl`, `selection_decisions.jsonl`, `review_queue.jsonl`, or `compile-export`.

## Operator flow

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
.venv-lexicon/bin/python -m tools.lexicon.cli build-phrases data/lexicon/phrasals/reviewed_phrasal_verbs.csv data/lexicon/idioms/reviewed_idioms.csv --output-dir data/lexicon/snapshots/phrases-demo
.venv-lexicon/bin/python -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
.venv-lexicon/bin/python -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode placeholder
.venv-lexicon/bin/python -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
.venv-lexicon/bin/python -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --max-concurrency 4 --resume
.venv-lexicon/bin/python -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
.venv-lexicon/bin/python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --dry-run
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US en-GB
.venv-lexicon/bin/python -m tools.lexicon.cli voice-import-db --input data/lexicon/voice/demo/voice_manifest.jsonl
.venv-lexicon/bin/python -m tools.lexicon.cli voice-sync-storage --source-reference demo --storage-kind s3 --storage-base https://cdn.example.com/voice --dry-run
```

## LLM configuration

Set these before realtime enrichment or live smoke runs:

- `LEXICON_LLM_BASE_URL`
- `LEXICON_LLM_MODEL`
- `LEXICON_LLM_API_KEY`
- optional `LEXICON_LLM_TRANSPORT=python|node`
- optional `LEXICON_LLM_REASONING_EFFORT=none|low|medium|high`

Defaults and current policy:

- default reasoning effort is `none`
- both realtime transports use the official OpenAI SDKs
- schema-backed enrichment uses strict `json_schema` structured output
- schema-backed requests do not downgrade to weaker JSON modes

## Tiny live smoke

```bash
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke run
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke --provider-mode openai_compatible --max-words 1 run
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke --provider-mode openai_compatible_node --max-words 1 run
```

## Voice generation

Voice generation is a separate derived-media step after review. It does not modify `approved.jsonl`.

Current defaults:

- provider: `google`
- family: `neural2`
- locales: `en-US`, `en-GB`
- supports reviewed `entry_type: word` and `entry_type: phrase` rows
- generates both `female` and `male` variants for each `word`, `definition`, and `example`
- voice IDs are configurable per run; the current defaults are:
  - `en-US`: female `en-US-Neural2-C`, male `en-US-Neural2-D`
  - `en-GB`: female `en-GB-Neural2-F`, male `en-GB-Neural2-B`

Prerequisite for live Google runs:

- install `tools/lexicon/requirements.txt`
- set `GOOGLE_APPLICATION_CREDENTIALS` to a readable service-account JSON file

Minimal flow:

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US,en-GB
.venv-lexicon/bin/python -m tools.lexicon.cli voice-import-db --input data/lexicon/voice/demo/voice_manifest.jsonl
```

Resume options:

- `--resume`: skip units already recorded as `generated` or `existing` in prior voice ledgers for the same `--output-dir`
- `--retry-failed-only`: rerun only units previously recorded in `voice_errors.jsonl`
- `--skip-failed`: with `--resume`, skip units previously recorded in `voice_errors.jsonl`
- file existence alone is not the resume source of truth anymore; prior ledgers drive the filter

The backend then resolves playback through `/api/words/voice-assets/{asset_id}/content`, while admin DB Inspector shows imported voice assets for both words and phrases.
Voice assets now keep `relative_path` plus a shared DB storage-policy reference internally. The storage policy itself owns the primary and optional fallback storage configuration. API responses still expose `storage_kind` and `storage_base` for compatibility.

Admin Voice page:

- open `/lexicon/voice`
- `Recent voice runs` reads CLI-produced run directories from `LEXICON_VOICE_ROOT`
- the run strip is paged horizontally with 2 runs per page so many historical runs do not make the page excessively tall
- `Current DB storage policies` shows the live DB policy records directly
- the current simplified model uses 3 DB policies: `word_default`, `definition_default`, and `example_default`
- policy cards expose direct edit affordances plus simple storage-state badges such as `local`, `remote`, and `fallback-enabled`
- `Voice Storage` rewrites the selected DB policy; it is policy-specific and independent from voice runs
- DB Inspector now shows both the runtime `playback_url` route and the primary resolved storage target for each voice asset
- selecting a run shows:
  - locale / voice-role / content-scope breakdowns
  - artifact download links for `voice_plan.jsonl`, `voice_manifest.jsonl`, and `voice_errors.jsonl` when present
  - latest manifest rows and latest error rows
- voice runs are informational only; they do not define or scope storage policies

## Admin portal workflow

The current admin workflow is:

- `/lexicon/ops`
  - snapshot-first workflow shell
- `/lexicon/compiled-review`
  - DB-backed review staging for compiled artifacts
- `/lexicon/jsonl-review`
  - file-backed review path for compiled artifacts, including phrase senses/examples/translations
- `/lexicon/import-db`
  - dry-run and final DB import for reviewed word and phrase outputs
- `/lexicon/db-inspector`
  - post-import verification against the live DB

`/lexicon/legacy` is now only a redirect to the current workflow and is not a separate review system.

## Related docs

- [OPERATOR_GUIDE.md](/Users/johnson/AI/src/words-v2/tools/lexicon/OPERATOR_GUIDE.md)
- [batch.md](/Users/johnson/AI/src/words-v2/tools/lexicon/docs/batch.md)
- [ADR-004-lexicon-canonical-final-ingestion-path.md](/Users/johnson/AI/src/words-v2/docs/decisions/ADR-004-lexicon-canonical-final-ingestion-path.md)
