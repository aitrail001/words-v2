# Lexicon Operator Guide

This runbook covers the active lexicon workflow only: word snapshot generation, curated phrase inventory build, shared enrichment, review, DB import, and optional derived voice generation/import.

## 1. Setup

```bash
make lexicon-install
.venv-lexicon/bin/python -m nltk.downloader wordnet omw-1.4
cp tools/lexicon/.env.example tools/lexicon/.env.local
set -a && source tools/lexicon/.env.local && set +a
```

If you want the Node-backed transport:

```bash
npm --prefix tools/lexicon ci
```

`make lexicon-install` creates or reuses the shared lexicon virtualenv at `~/.cache/words/venvs/` and keeps a worktree-local `.venv-lexicon` link when possible. If your current worktree already has a real `.venv-lexicon` directory, the target leaves it alone.

Important:

- `tools/lexicon/.env.local` is not auto-loaded by the CLI
- browser/admin apps should use same-origin `/api`; container proxying is handled by `BACKEND_URL`
- default lexicon reasoning effort is `none`
- `data/` is local-only operational storage and is not part of the Git-synced code checkout
- keep using `data/lexicon/...` paths locally, but do not treat snapshot artifacts as repo-tracked fixtures

## 2. Canonical workflow

1. `build-base`
2. optional `build-phrases`
3. optional ambiguous-form adjudication
3. `enrich`
4. `validate`
5. review `words.enriched.jsonl`
6. `import-db` from `reviewed/approved.jsonl`
7. optional `voice-generate` from `reviewed/approved.jsonl`
8. optional `voice-import-db` from `voice_manifest.jsonl`

Realtime writes final accepted word and phrase rows directly to `words.enriched.jsonl`.
Batch materializes accepted word and phrase rows into that same file later via `batch-ingest`.

## 3. Build a snapshot

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-base --top-words 1000 --output-dir data/lexicon/snapshots/words-1000
python3 -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
```

Use `data/lexicon/...` as a local workspace. Long-running enrich, batch, review-export, and import-prep commands should operate there so Git code sync stays separate from runtime artifact churn.

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
.venv-lexicon/bin/python -m tools.lexicon.cli build-phrases data/lexicon/phrasals/reviewed_phrasal_verbs.csv data/lexicon/idioms/reviewed_idioms.csv --output-dir data/lexicon/snapshots/phrases-demo
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
.venv-lexicon/bin/python -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
.venv-lexicon/bin/python -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode auto
.venv-lexicon/bin/python -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
```

## 6. Realtime enrichment

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --max-concurrency 4 --resume
```

Behavior:

- reads `lexemes.jsonl` and optional `phrases.jsonl`
- generates one strict payload per word or phrase entry
- validates/QCs immediately
- retries repairable failures
- writes accepted rows directly to `words.enriched.jsonl` as each lexeme finishes successfully
- keeps resume sidecars:
  - `enrich.checkpoint.jsonl` = authoritative completed skip ledger for `--resume`
  - `enrich.decisions.jsonl` = completed decision ledger
  - `enrich.failures.jsonl` = append-only failure history across retries and resumes

## 7. Batch enrichment

Use batch when you want deferred file-based generation rather than inline calls.

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli batch-prepare --snapshot-dir data/lexicon/snapshots/demo
.venv-lexicon/bin/python -m tools.lexicon.cli batch-status --snapshot-dir data/lexicon/snapshots/demo
.venv-lexicon/bin/python -m tools.lexicon.cli batch-ingest --snapshot-dir data/lexicon/snapshots/demo --input data/lexicon/snapshots/demo/batches/output.jsonl
```

Behavior:

- `batch-prepare` writes request ledgers
- phrase request rows use the strict phrase schema/prompt contract
- `batch-ingest` applies the same word-level and phrase-level validation/materialization used by realtime
- accepted rows append to `words.enriched.jsonl`
- failed rows go to `words.regenerate.jsonl`

## 8. Validate

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
.venv-lexicon/bin/python -m tools.lexicon.cli validate --compiled-input data/lexicon/snapshots/demo/words.enriched.jsonl
```

## 9. Review in admin

Current admin tools:

- `/lexicon/ops`
- `/lexicon/compiled-review`
- `/lexicon/jsonl-review`
- `/lexicon/import-db`
- `/lexicon/db-inspector`
- `/lexicon/voice`

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
.venv-lexicon/bin/python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --dry-run
.venv-lexicon/bin/python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --source-type lexicon_snapshot --source-reference demo
```

`import-db` is the only final write path into lexicon DB tables, including approved phrase rows.

## 11. Generate voice artifacts

Voice generation is a separate derived-media step. It reads reviewed `approved.jsonl`, writes audio files plus JSONL ledgers, and does not mutate the reviewed learner rows.

Current defaults:

- provider: `google`
- family: `neural2`
- locales: `en-US`, `en-GB`
- supports reviewed `entry_type: word` and `entry_type: phrase` rows
- both `female` and `male` variants generated for each `word`, `definition`, and `example`
- default Google voices:
  - `en-US`: female `en-US-Neural2-C`, male `en-US-Neural2-D`
  - `en-GB`: female `en-GB-Neural2-F`, male `en-GB-Neural2-B`

Live Google prerequisite:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

Generate voice artifacts:

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US,en-GB
```

Resume options:

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US,en-GB --resume
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US,en-GB --resume --retry-failed-only
.venv-lexicon/bin/python -m tools.lexicon.cli voice-generate --input data/lexicon/snapshots/demo/reviewed/approved.jsonl --output-dir data/lexicon/voice/demo --provider google --family neural2 --locales en-US,en-GB --resume --skip-failed
```

Outputs:

- `voice_plan.jsonl` = planned work units
- `voice_manifest.jsonl` = successful generated assets and metadata
- `voice_errors.jsonl` = failed work units and error details
- audio files under the selected `--output-dir`, organized by provider/family/locale
- structured console progress, including startup config, planning counts, periodic progress snapshots, concise failure lines, and completion totals

Notes:

- voice IDs are defaults, not hardcoded behavior; override them through command arguments/config when needed
- the tool flushes results as units complete, so one failed or slow word does not block unrelated outputs
- reruns are safe because paths are deterministic and manifest rows are keyed by content scope, locale, voice role, provider/family, and source text hash
- `--resume` uses prior `voice_manifest.jsonl` and `voice_errors.jsonl` ledgers to decide what is already complete
- `--retry-failed-only` restricts the rerun to units previously recorded as failed and is intended to be used with `--resume`
- `--skip-failed` keeps `--resume` from retrying prior failed units when the operator wants to leave known-bad rows alone for the current pass

## 12. Import voice metadata to DB

After `import-db` has loaded the reviewed learner rows, import the generated voice manifest:

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli voice-import-db --input data/lexicon/voice/demo/voice_manifest.jsonl
```

Behavior:

- loads normalized voice metadata into `lexicon_voice_assets`
- links rows to imported words, meanings, examples, phrases, phrase senses, and phrase examples
- preserves `relative_path` on each asset and assigns each asset to a shared DB storage policy so playback can resolve through primary and optional fallback storage directly from the policy
- backend playback resolves through `/api/words/voice-assets/{asset_id}/content`
- admin DB Inspector shows imported voice assets on both word and phrase detail, including the runtime playback route and the primary resolved storage target
- admin Lexicon Voice includes the voice-storage rewrite panel with both Dry Run and Apply actions for repointing imported assets after a cloud copy
- the Lexicon Voice page shows the latest rewrite result summary, including matched count, updated count, primary storage, and fallback storage
- the Lexicon Voice page shows the current persisted storage policies from the DB directly
- the current simplified storage model uses exactly 3 DB policies: `word_default`, `definition_default`, and `example_default`
- policy cards include direct `Edit policy` actions and storage-state badges
- policy rewrites in the admin UI apply to the explicitly selected policy rows; `sourceReference` is only a filter on the DB policy list, not the direct rewrite target
- the Lexicon Voice page now also shows recent voice runs from the configured voice artifact root, including planned/generated/existing/failed counts per run directory
- recent runs are shown in a paged horizontal strip with 2 runs per page so many runs do not prolong the page
- clicking a run in Lexicon Voice now shows the latest manifest rows and latest error rows for that run
- run detail also shows locale / voice-role / content-scope breakdowns plus artifact download links from the CLI-ledger directory
- artifact downloads on `/lexicon/voice` now use authenticated admin fetches; opening the raw `/api/lexicon-ops/voice-runs/.../artifacts/...` URL directly without admin auth will return `Not authenticated`
- voice runs are separate operational history; they do not scope or define storage policies

Live demo references currently loaded in local dev:

- `/lexicon/voice`
  - shows the 3 current DB policies directly
  - recent runs currently include `voice-admin-demo-a-run` and `voice-admin-demo-b-run`

## 13. Rewrite voice storage from CLI

Use this after copying generated voice files from local output to cloud/object storage and you want the DB to point the matching storage policies at a new primary and optional fallback storage target.

```bash
.venv-lexicon/bin/python -m tools.lexicon.cli voice-sync-storage --source-reference demo --storage-kind s3 --storage-base https://cdn.example.com/voice --dry-run
.venv-lexicon/bin/python -m tools.lexicon.cli voice-sync-storage --source-reference demo --storage-kind s3 --storage-base https://cdn.example.com/voice
.venv-lexicon/bin/python -m tools.lexicon.cli voice-sync-storage --source-reference demo --storage-kind s3 --storage-base https://cdn.example.com/voice --fallback-storage-kind http --fallback-storage-base https://backup.example.com/voice
```

Behavior:

- updates the selected storage policy or matching CLI-scoped policies to use the requested primary `storage_kind` and `storage_base`
- optionally sets or clears fallback storage via `--fallback-storage-kind` / `--fallback-storage-base`
- keeps `relative_path` unchanged
- supports optional `--provider`, `--family`, and `--locale` filters
- mirrors the admin Lexicon Voice rewrite operation for terminal workflows

## 14. Troubleshooting

- Ops page shows `Failed to fetch`
  - ensure admin/frontend browser API base is `/api`
  - ensure server-side `BACKEND_URL` points at the backend
- Enrichment fails immediately on structured outputs
  - verify the endpoint supports Responses API strict `json_schema`
- A word keeps failing validation
  - inspect `enrich.failures.jsonl` or `words.regenerate.jsonl`
- Import does not see reviewed rows
  - confirm `reviewed/approved.jsonl` exists under the selected snapshot
- `voice-generate` fails immediately
  - confirm `google-cloud-texttospeech` is installed in `.venv-lexicon`
  - confirm `GOOGLE_APPLICATION_CREDENTIALS` points to a readable service-account file
- `voice-import-db` reports missing words/meanings/examples
  - run `import-db` on the same reviewed `approved.jsonl` first
  - confirm the voice manifest was generated from the same reviewed content set
- Local code checkout is behind remote after a merge
  - `git fetch origin && git pull --ff-only`
  - remember that restarting a long-running lexicon command is required before it can pick up newly pulled code

## 15. Helper scripts

Monitor realtime enrichment sidecars:

```bash
zsh tools/lexicon/scripts/monitor-enrich.zsh data/lexicon/snapshots/demo
zsh tools/lexicon/scripts/monitor-enrich.zsh --no-tail data/lexicon/snapshots/demo
```

Monitor voice generation ledgers:

```bash
zsh tools/lexicon/scripts/monitor-voice.zsh data/lexicon/voice/demo
zsh tools/lexicon/scripts/monitor-voice.zsh --no-tail data/lexicon/voice/demo
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
