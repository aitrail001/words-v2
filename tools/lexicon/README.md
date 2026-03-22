# Lexicon Tool

Offline/admin lexicon pipeline for building word and phrase snapshots, generating learner-facing enrichments, reviewing them, and importing approved rows into the DB.

## Current contract

The active pipeline is lexeme-first for words, with curated phrase inventory support on the same compiled/review/import contract:

1. `build-base`
2. optional `build-phrases`
2. optional ambiguous-form adjudication
3. `enrich`
4. `validate`
5. human review of `words.enriched.jsonl`
6. `import-db` from reviewed `approved.jsonl`

Realtime enrichment writes final compiled word and phrase rows directly to `words.enriched.jsonl`.
Batch enrichment can still use intermediate request/result ledgers, but accepted word and phrase rows are materialized into the same `words.enriched.jsonl` contract.

Legacy sense-selection and staged-selection review flows are removed from the supported operator surface.

## Main commands

- `python3 -m tools.lexicon.cli build-base ...`
  - builds a normalized lexeme snapshot
  - writes `lexemes.jsonl` plus canonicalization/operator sidecars
- `python3 -m tools.lexicon.cli detect-ambiguous-forms ...`
  - emits only unresolved canonicalization tails
- `python3 -m tools.lexicon.cli adjudicate-forms ...`
  - resolves bounded ambiguous-form tails
- `python3 -m tools.lexicon.cli build-phrases --input ... --output-dir ...`
  - builds curated phrase inventory rows from one or more reviewed CSVs
  - writes `phrases.jsonl`
- `python3 -m tools.lexicon.cli enrich --snapshot-dir ...`
  - realtime per-entry enrichment
  - reads `lexemes.jsonl` and optional `phrases.jsonl`
  - writes `words.enriched.jsonl`
  - keeps `enrich.checkpoint.jsonl`, `enrich.decisions.jsonl`, `enrich.failures.jsonl`
- `python3 -m tools.lexicon.cli validate --snapshot-dir ...`
  - validates snapshot inputs and outputs
- `python3 -m tools.lexicon.cli validate --compiled-input ...`
  - validates compiled learner-facing JSONL rows
- `python3 -m tools.lexicon.cli batch-prepare --snapshot-dir ...`
  - writes batch request ledgers
- `python3 -m tools.lexicon.cli batch-ingest --snapshot-dir ...`
  - ingests completed batch output JSONL
  - writes accepted rows to `words.enriched.jsonl`
  - writes failed rows to `words.regenerate.jsonl`
- `python3 -m tools.lexicon.cli import-db --input ...`
  - dry-runs or imports reviewed learner-facing rows into the DB

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

The active pipeline no longer relies on `senses.jsonl`, `concepts.jsonl`, `selection_decisions.jsonl`, `review_queue.jsonl`, or `compile-export`.

## Operator flow

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-phrases --input data/lexicon/phrasals/reviewed_phrasal_verbs.csv --input data/lexicon/idioms/reviewed_idioms.csv --output-dir data/lexicon/snapshots/phrases-demo
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode placeholder
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4 --resume
python3 -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --dry-run
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

- [OPERATOR_GUIDE.md](/Users/johnson/AI/src/words-v2/.worktrees/feat_phrase_enrichment_20260323/tools/lexicon/OPERATOR_GUIDE.md)
- [batch.md](/Users/johnson/AI/src/words-v2/.worktrees/feat_phrase_enrichment_20260323/tools/lexicon/docs/batch.md)
- [ADR-004-lexicon-canonical-final-ingestion-path.md](/Users/johnson/AI/src/words-v2/.worktrees/feat_phrase_enrichment_20260323/docs/decisions/ADR-004-lexicon-canonical-final-ingestion-path.md)
