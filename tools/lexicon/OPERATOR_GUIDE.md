# Lexicon Operator Guide

This runbook covers the active lexicon workflow only: word snapshot generation, curated phrase inventory build, shared enrichment, review, and DB import.

## 1. Setup

```bash
python3 -m pip install -r tools/lexicon/requirements.txt
python3 -m nltk.downloader wordnet omw-1.4
cp tools/lexicon/.env.example tools/lexicon/.env.local
set -a && source tools/lexicon/.env.local && set +a
```

If you want the Node-backed transport:

```bash
npm --prefix tools/lexicon ci
```

Important:

- `tools/lexicon/.env.local` is not auto-loaded by the CLI
- browser/admin apps should use same-origin `/api`; container proxying is handled by `BACKEND_URL`
- default lexicon reasoning effort is `none`

## 2. Canonical workflow

1. `build-base`
2. optional `build-phrases`
3. optional ambiguous-form adjudication
3. `enrich`
4. `validate`
5. review `words.enriched.jsonl`
6. `import-db` from `reviewed/approved.jsonl`

Realtime writes final accepted word and phrase rows directly to `words.enriched.jsonl`.
Batch materializes accepted word and phrase rows into that same file later via `batch-ingest`.

## 3. Build a snapshot

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-base --top-words 1000 --output-dir data/lexicon/snapshots/words-1000
python3 -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
```

Current base artifacts:

- `lexemes.jsonl`
- `canonical_entries.jsonl`
- `canonical_variants.jsonl`
- `generation_status.jsonl`
- optional `ambiguous_forms.jsonl`
- optional `form_adjudications.jsonl`

The active snapshot contract no longer uses `senses.jsonl` or `concepts.jsonl`.

## 4. Build curated phrase inventory

Use this when you want phrasal verbs, idioms, or other reviewed phrase CSV rows to flow through the same enrichment and review path as words.

```bash
python3 -m tools.lexicon.cli build-phrases --input data/lexicon/phrasals/reviewed_phrasal_verbs.csv --input data/lexicon/idioms/reviewed_idioms.csv --output-dir data/lexicon/snapshots/phrases-demo
```

Behavior:

- reads one or more reviewed CSV inventories
- maps reviewed labels into the bounded phrase taxonomy
- dedupes by normalized phrase form
- writes `phrases.jsonl`
- preserves raw reviewed labels and source metadata in `source_provenance` and `seed_metadata`

## 5. Optional ambiguous-form adjudication

Use this only for bounded canonicalization tails.

```bash
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode auto
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
```

## 6. Realtime enrichment

```bash
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4 --resume
```

Behavior:

- reads `lexemes.jsonl` and optional `phrases.jsonl`
- generates one strict payload per word or phrase entry
- validates/QCs immediately
- retries repairable failures
- writes accepted rows directly to `words.enriched.jsonl`
- keeps resume sidecars:
  - `enrich.checkpoint.jsonl`
  - `enrich.decisions.jsonl`
  - `enrich.failures.jsonl`

## 7. Batch enrichment

Use batch when you want deferred file-based generation rather than inline calls.

```bash
python3 -m tools.lexicon.cli batch-prepare --snapshot-dir data/lexicon/snapshots/demo
python3 -m tools.lexicon.cli batch-status --snapshot-dir data/lexicon/snapshots/demo
python3 -m tools.lexicon.cli batch-ingest --snapshot-dir data/lexicon/snapshots/demo --input data/lexicon/snapshots/demo/batches/output.jsonl
```

Behavior:

- `batch-prepare` writes request ledgers
- phrase request rows use the strict phrase schema/prompt contract
- `batch-ingest` applies the same word-level and phrase-level validation/materialization used by realtime
- accepted rows append to `words.enriched.jsonl`
- failed rows go to `words.regenerate.jsonl`

## 8. Validate

```bash
python3 -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
python3 -m tools.lexicon.cli validate --compiled-input data/lexicon/snapshots/demo/words.enriched.jsonl
```

## 9. Review in admin

Current admin tools:

- `/lexicon/ops`
- `/lexicon/compiled-review`
- `/lexicon/jsonl-review`
- `/lexicon/import-db`
- `/lexicon/db-inspector`

Recommended order:

1. start in `/lexicon/ops`
2. open Compiled Review or JSONL Review for `words.enriched.jsonl`
3. export/materialize reviewed outputs under `reviewed/`
4. open Import DB for `reviewed/approved.jsonl`
5. verify in DB Inspector

Reviewed artifact contract:

- `words.enriched.jsonl` = immutable compiled artifact before review
- `reviewed/approved.jsonl` = approved rows for import
- `reviewed/rejected.jsonl` = rejected rows plus decision metadata
- `reviewed/regenerate.jsonl` = rerun request set
- `reviewed/review.decisions.jsonl` = canonical decision ledger

Phrase rows stay inside this same workflow. Both review pages now surface phrase kind, first-sense definition, example, and translations without requiring raw JSON inspection.

The admin portal no longer supports the old staged-selection review flow.

## 10. Import to DB

```bash
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --dry-run
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --source-type lexicon_snapshot --source-reference demo
```

`import-db` is the only final write path into lexicon DB tables, including approved phrase rows.

## 11. Troubleshooting

- Ops page shows `Failed to fetch`
  - ensure admin/frontend browser API base is `/api`
  - ensure server-side `BACKEND_URL` points at the backend
- Enrichment fails immediately on structured outputs
  - verify the endpoint supports Responses API strict `json_schema`
- A word keeps failing validation
  - inspect `enrich.failures.jsonl` or `words.regenerate.jsonl`
- Import does not see reviewed rows
  - confirm `reviewed/approved.jsonl` exists under the selected snapshot

## 11. Helper scripts

Monitor realtime enrichment sidecars:

```bash
zsh tools/lexicon/scripts/monitor-enrich.zsh data/lexicon/snapshots/demo
zsh tools/lexicon/scripts/monitor-enrich.zsh --no-tail data/lexicon/snapshots/demo
```

Show discarded realtime decisions and why:

```bash
python3 tools/lexicon/scripts/show-discarded.py data/lexicon/snapshots/demo
python3 tools/lexicon/scripts/show-discarded.py data/lexicon/snapshots/demo/enrich.decisions.jsonl --json
```

Show realtime failures and why:

```bash
python3 tools/lexicon/scripts/show-failures.py data/lexicon/snapshots/demo
python3 tools/lexicon/scripts/show-failures.py data/lexicon/snapshots/demo/enrich.failures.jsonl --json
```
