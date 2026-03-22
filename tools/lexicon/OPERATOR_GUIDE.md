# Lexicon Operator Guide

This guide is for the offline/admin lexicon pipeline that builds snapshot files, enriches them for learners, validates them, compiles a DB-ready JSONL export, and optionally imports that export into the local database.

## 1. What this tool is for

Use `tools/lexicon` when you want to:
- build a WordNet + `wordfreq` based lexical snapshot
- enrich learner-facing fields with an LLM in a separate admin step
- optionally rerank grounded WordNet candidates with an LLM before deciding whether the selector needs further tuning
- run built-in tuning/holdout benchmarks to compare deterministic selection against multiple grounded rerank modes
- validate and compile the snapshot into `words.enriched.jsonl`
- import the compiled output into the local DB

This tool is intentionally separate from the app runtime path.

## 2. One-time setup

Install Python dependencies and the required WordNet corpora:

```bash
python3 -m pip install -r tools/lexicon/requirements.txt
python3 -m nltk.downloader wordnet omw-1.4
```

If you plan to use a Node-backed custom gateway path, install the tool-local Node dependency too:

```bash
npm --prefix tools/lexicon ci
```

## 3. Environment setup

Copy the tool-local example file, then export it into your shell:

```bash
cp tools/lexicon/.env.example tools/lexicon/.env.local
set -a && source tools/lexicon/.env.local && set +a
```

Important notes:
- `tools/lexicon/.env.local` is not auto-loaded by the CLI; you must source it yourself.
- Keep real LLM keys only in your local `.env.local` or another secret store.
- Prefer `LEXICON_LLM_BASE_URL` over the legacy alias `LEXICON_LLM_PROVIDER`.
- `LEXICON_LLM_REASONING_EFFORT` is optional and supports `low`, `medium`, or `high` for compatible Responses APIs.

## 3.5 Canonical final DB write path

Use this as the canonical final DB write path for generated learner-facing lexicon data:

1. `build-base`
2. optional ambiguous-form adjudication flow (`detect-ambiguous-forms` / `adjudicate-forms` / rerun `build-base --adjudications ...`)
3. optional review-prep flow
4. `enrich`
5. `validate --snapshot-dir`
6. `compile-export`
7. `validate --compiled-input`
8. `import-db`

Important:
- staged review is the review/decision layer
- `compile-export -> import-db` is the canonical final learner-enrichment write path
- lexicon-owned DB tables now live in the dedicated Postgres `lexicon` schema, while runtime/app tables remain outside that schema in the same database
- for compiled per-word artifacts, `import-db` now groups senses that share the same `generation_run_id` into one DB enrichment run row per word request
- the narrower staged-review publish path is transitional and should not be treated as the main learner-enrichment publisher
- ambiguous-form adjudication is optional and only operates on `unknown_needs_llm` canonicalization tails with bounded `candidate_forms`
- unresolved ambiguous tails are deferred from `lexemes.jsonl` / `senses.jsonl` until adjudication; inspect them with `status-entry` instead of treating them as ready for enrichment
- `build-base` now performs a bulk DB existence check on canonical headwords when `--database-url` or `DATABASE_URL_SYNC` is configured, and skips already-published words in that DB; use `--rerun-existing` when you intentionally want to regenerate them

For the minimum pass/fail closure gate, use `docs/runbooks/lexicon-working-gate.md`.

## 4. Recommended operator flow

Build a normalized snapshot first:

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-base --top-words 1000 --output-dir data/lexicon/snapshots/words-1000
python3 -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
# build-base now deterministically collapses obvious inflectional duplicates like things->thing and gives->give while keeping lexicalized forms like left as separate entries linked to their base family
# it also skips canonical words already present in the local DB unless you pass --rerun-existing
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode placeholder
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
python3 -m tools.lexicon.cli lookup-entry --snapshot-dir data/lexicon/snapshots/demo things
python3 -m tools.lexicon.cli status-entry --snapshot-dir data/lexicon/snapshots/demo --check-db thing
```

Enrich the learner-facing layer:

```bash
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4
# per_word mode on the 30K rollout path is word-only; the prompt repeats the hard 8/6/4 meaning cap, requires a JSON object only, retries repairable invalid payloads, and requires learner translations for zh-Hans/es/ar/pt-BR/ja
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4 --model gpt-5.4 --reasoning-effort low
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/words-1000 --provider-mode auto --mode per_word --max-concurrency 4 --request-delay-seconds 1.0 --max-failures 25
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/words-1000 --provider-mode auto --mode per_word --max-concurrency 4 --request-delay-seconds 1.0 --max-failures 25 --resume
# large per_word runs now append directly to enrichments.jsonl and keep enrich.checkpoint.jsonl + enrich.decisions.jsonl + enrich.failures.jsonl beside the snapshot by default
```

Validate the normalized snapshot plus enrichments:

```bash
python3 -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
```

For staged common-word runs, the operator-safe pattern is:

- `build-base --rollout-stage 100`, verify the outputs, then run `enrich --mode per_word`
- scale to `--rollout-stage 1000` only after the checkpoint/resume path is clean
- keep `enrich.checkpoint.jsonl`, `enrich.decisions.jsonl`, and `enrich.failures.jsonl` with the snapshot so `--resume` can restart without losing completed lexemes or discard audit history
- use `--request-delay-seconds` to respect gateway pacing limits and `--max-failures` to fail loudly before burning through a large batch

Compile the final export:

```bash
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --decision-filter mode_c_safe --output data/lexicon/snapshots/demo/words.mode-c-safe.enriched.jsonl
```

`compile-export` now also writes shared review-prep sidecars beside each compiled output:

- `<compiled-output>.review_qc.jsonl`
- `<compiled-output>.review_queue.jsonl`

Those sidecars are generated from the same normalized `word`, `phrase`, and `reference` rows that feed admin review. Realtime exports now pass through the same post-normalization QC/label/review-queue preparation path that batch uses, while still keeping the immediate realtime schema validation in place.

### 4.2 Compiled-review staging before final import

For learner-facing compiled artifacts, there is now a separate admin review stage before `import-db`.

Use it when you want to inspect compiled JSONL rows in the admin app instead of importing them directly into final lexicon tables.

Flow:

1. Produce `words.enriched.jsonl`, `phrases.enriched.jsonl`, or `references.enriched.jsonl`
2. Open the admin app at `/lexicon/compiled-review`
3. Import the compiled artifact into the compiled-review staging surface
4. Approve/reject/reopen rows in the UI
5. Export:
   - approved rows
   - rejected overlays
   - regenerate rows
   - canonical decisions
6. Optionally run `review-materialize` to re-materialize file outputs from canonical decisions
7. Run `import-db` only on approved compiled rows

Important:

- This import is review staging only.
- It writes to dedicated `lexicon_artifact_review_*` tables, not to the final lexicon `word` / `meaning` / `phrase_entries` / `reference_entries` tables.
- The final learner-facing DB write path remains `compile-export -> import-db`.

### 4.3 Admin workflow map

The admin portal now exposes the current lexicon workflow as separate tools instead of a single mixed review page:

- `/lexicon/ops`
  - canonical workflow shell
  - inspects `data/lexicon/snapshots/*`
  - derives the current workflow stage, preferred review artifact, preferred import artifact, and next recommended action from snapshot artifacts
  - shows which steps still happen outside the admin portal
  - disables review/import actions when the required compiled or approved artifacts do not exist yet, instead of sending operators into empty downstream pages
  - deep-links into review/import/inspection flows with the selected snapshot prefilled
- `/lexicon/compiled-review`
  - DB-backed review staging for immutable compiled artifacts
  - imports compiled JSONL into review tables, not final lexicon tables
  - supports both file upload and import-by-path for an existing compiled artifact selected in `/lexicon/ops`
  - when launched from `/lexicon/ops`, it should auto-import the selected compiled artifact into review staging and keep snapshot/source-reference context visible in the batch list
- `/lexicon/jsonl-review`
  - file-backed review path for compiled artifacts plus `review.decisions.jsonl`
  - keeps JSONL as source of truth and never imports review state into review tables
  - when launched from `/lexicon/ops`, it should auto-load the selected artifact and sidecar paths instead of opening as a blank form
- `/lexicon/import-db`
  - explicit final import step for approved compiled JSONL
  - supports dry-run and real import
  - when launched from `/lexicon/ops`, it should arrive prefilled and auto-run the dry-run, but still require an explicit click for the final DB write
- `/lexicon/db-inspector`
  - post-import verification against the real lexicon DB
- `/lexicon/legacy`
  - deprecated `selection_decisions.jsonl` review surface kept only for historical staged-selection flows

Recommended operator order:

1. start in `/lexicon/ops`
2. follow the stage guidance shown for the selected snapshot
3. use `/lexicon/compiled-review` as the default review path, or `/lexicon/jsonl-review` as the alternate file-backed path
4. export or materialize approved JSONL
5. run `/lexicon/import-db`
6. confirm the final state in `/lexicon/db-inspector`

Important:

- the admin portal is still a workflow shell around an offline lexicon pipeline
- `build-base`, optional ambiguous-form adjudication, `enrich`, `validate`, `compile-export`, and the batch prepare/submit/status/ingest/qc steps still happen outside the portal
- `/lexicon/ops` should tell you which of those steps are still outstanding for the selected snapshot
- the admin frontend should use same-origin `/api` in the browser and a server-side `BACKEND_URL` proxy; do not flip `NEXT_PUBLIC_API_URL` between `localhost` and `backend` just to switch between macOS browser use and Docker-internal Playwright

Run an import dry-run summary:

```bash
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
python3 -m tools.lexicon.cli rerank-senses --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --candidate-source candidates --candidate-limit 8
python3 -m tools.lexicon.cli compare-selection --snapshot-dir data/lexicon/snapshots/demo --rerank-file data/lexicon/snapshots/demo/sense_reranks.jsonl
python3 -m tools.lexicon.cli benchmark-selection --output-dir /tmp/lexicon-benchmark --dataset tuning --dataset holdout --with-rerank --provider-mode auto --candidate-source selected_only --candidate-source candidates --candidate-source full_wordnet
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

### 4.1 Optional ambiguous-form adjudication

Use this only when deterministic canonicalization emitted `ambiguous_forms.jsonl` rows that you want to resolve before enrichment:

```bash
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode auto
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
```

Contract:
- the adjudicator may only choose the surface form or one of deterministic `candidate_forms`
- the artifacts are replayable and can be checked into an operator run directory if needed
- the default rollout path is still deterministic-only unless you explicitly pass `--adjudications`
- use adjudication for true canonicalization tails like `ringed -> ring`, not for common headwords that still build directly

## 5. Provider modes

`enrich` and `adjudicate-forms` support these provider modes:
- `auto` — use `openai_compatible_node` when `LEXICON_LLM_TRANSPORT=node`, otherwise use the default endpoint path when LLM env is present, or placeholder mode when not
- `placeholder` — generate deterministic fake learner-facing data for local non-LLM testing
- `openai_compatible` — use the Python OpenAI-compatible Responses transport
- `openai_compatible_node` — use the official Node OpenAI SDK transport

## 6. Custom OpenAI-compatible gateways

If your gateway works with the official Node OpenAI SDK but rejects the Python transport, store the values in `tools/lexicon/.env.local`, source that file into your shell, and set:

For GitHub Actions, do **not** rely on local `.env` files. Configure the same values in the protected GitHub environment `lexicon-llm` instead:

- environment variable `LEXICON_LLM_BASE_URL`
- environment variable `LEXICON_LLM_MODEL`
- optional environment variable `LEXICON_LLM_TRANSPORT=node`
- environment secret `LEXICON_LLM_API_KEY`

```bash
LEXICON_LLM_BASE_URL='https://api.nwai.cc'
LEXICON_LLM_MODEL='gpt-5.1'
LEXICON_LLM_TRANSPORT='node'
```

Keep `LEXICON_LLM_API_KEY` in your local `tools/lexicon/.env.local` instead of pasting it directly into shell history. Then use either the normal `enrich` flow with `--provider-mode auto` or the bounded smoke command:

```bash
python3 -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-smoke run
python3 -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-smoke --max-words 2 --max-senses 2 --model gpt-5.4 --reasoning-effort low run set
```

## 6.5 Learner-priority rubric

Use `tools/lexicon/SELECTION_RUBRIC.md` when judging whether deterministic selection or `rerank-senses` produced a better learner-facing candidate set. The rerank step is grounded: it may only choose from provided `wn_synset_id` candidates and cannot invent new senses.

Mode guidance:
- `selected_only` is safest when you want an LLM review of ordering without allowing any new grounded senses into the set.
- `candidates` is the recommended benchmark and premium-quality mode because it can fix deterministic misses while staying within a bounded shortlist.
- `full_wordnet` is useful for evaluation and exploration, but it is slower and more likely to surface debatable tail substitutions.

## 6.6 Risk scoring and review preparation

Use this offline three-step flow when you want staged review instead of publishing deterministic selection directly:

```bash
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

Interpretation:
- `risk_band=deterministic_only` means no rerank is needed for that lexeme in the staged flow
- `risk_band=rerank_recommended` means rerank is useful but may still auto-accept if the change is small and stable
- `risk_band=rerank_and_review_candidate` means the lexeme is a stronger human-review candidate even after rerank
- `auto_accepted=true` means rerank was applied and accepted without human review
- `review_required=true` means the row should stay staged and also appear in `review_queue.jsonl`

This stage is intentionally review-oriented:
- `selection_decisions.jsonl` keeps the deterministic decision, risk score, candidate metadata, and rerank outcome together
- `review_queue.jsonl` is the bounded list humans should actually inspect
- the admin lexicon portal can now import staged decisions and show current selected senses, selection source, candidate gloss/definition, POS, and rank/reason hints for review
- `compile-export --decisions ... --decision-filter mode_c_safe` is the first-class safe-export path for direct DB import of lexemes that are deterministic-only or auto-accepted and not still marked `review_required=true`
- filtered compile runs now fail loudly if `--decisions` and `--decision-filter` are not provided together, which prevents accidental unfiltered exports

## 7. Import into the local DB

For a real non-dry-run import, your backend DB settings must be available in the shell. The backend settings loader now ignores unrelated extra env keys in the repo-root `.env`, so this command can run from the normal repository root flow. The importer writes into lexicon-owned tables under the dedicated `lexicon` schema while continuing to share the same database server as the backend runtime tables:

```bash
python3 -m tools.lexicon.cli import-db \
  --input data/lexicon/snapshots/demo/words.enriched.jsonl \
  --source-type lexicon_snapshot \
  --source-reference demo-snapshot-20260307 \
  --language en
```

Use a clean local DB or isolated temporary Postgres instance if your main dev DB has unrelated schema drift.

## 8. Output files and linking

A single snapshot directory links together the pipeline stages:
- `lexemes.jsonl` holds lemma-level records plus shared entry metadata (`entry_id`, `entry_type`, `normalized_form`, `source_provenance`)
- `senses.jsonl` links back to lexemes by `lexeme_id`
- `enrichments.jsonl` links to senses by `sense_id`
- `selection_decisions.jsonl` stores deterministic selection, risk scoring, and rerank/review state for each lexeme, and can drive both admin review import and `compile-export --decision-filter mode_c_safe`
- `review_queue.jsonl` stores only the lexemes still marked `review_required=true` after bounded rerank
- `words.enriched.jsonl` is the compiled learner-facing export used by `import-db`, including sense-level enrichment provenance needed for local DB writeback

Re-run any stage independently as long as the required upstream files already exist in that snapshot directory.

## 9. Common failure modes

- Missing WordNet or `wordfreq` dependencies: re-run `python3 -m pip install -r tools/lexicon/requirements.txt` and `python3 -m nltk.downloader wordnet omw-1.4`
- Missing LLM env for real enrichment or risky-word review prep: confirm `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, and `LEXICON_LLM_API_KEY` are exported in the current shell
- Cloudflare/custom gateway rejects Python transport: install Node deps with `npm --prefix tools/lexicon ci`, then set `LEXICON_LLM_TRANSPORT=node`
- If the GitHub workflow still returns Cloudflare challenge HTML or HTTP 403 after switching to `LEXICON_LLM_TRANSPORT=node`, the GitHub-hosted runner is being blocked upstream. In that case, use a self-hosted runner or add gateway allow/bypass rules for the CI client/API path.
- Import path fails against a drifted local DB: use a clean local DB or isolated temporary Postgres instance instead of forcing the import into a broken dev database
- Import wrote only core words/meanings when you expected learner-facing extras: confirm the compiled file came from the current `compile-export` step and not an older minimal `words.enriched.jsonl`

## 10. Operator evidence checklist

After a successful run, keep or inspect these artifacts:
- the snapshot directory containing `lexemes.jsonl`, `senses.jsonl`, `enrichments.jsonl`, and any staged review outputs
- the staged review artifacts `selection_decisions.jsonl` and optional `review_queue.jsonl` when you run the review-prep flow
- the compiled export `words.enriched.jsonl`
- the exact command lines used for `build-base`, `enrich`, `score-selection-risk`, `prepare-review`, `validate`, `compile-export`, and optional `import-db`
- the summary counts printed by the CLI so you can compare later reruns, rerank decisions, and imports, including examples/relations and enrichment job/run reuse

## 11. See also

- `tools/lexicon/README.md`
- `tools/lexicon/.env.example`
- `.github/workflows/lexicon-openai-compatible-smoke.yml`
- `docs/runbooks/lexicon-working-gate.md`
- `docs/plans/2026-03-08-lexicon-future-improvements-todo.md`


## Translation scope in this slice

- `enrich` now emits required learner translations for `zh-Hans`, `es`, `ar`, `pt-BR`, and `ja` on each sense.
- `compile-export` preserves those translations in compiled sense rows.
- `import-db` currently persists translated definitions into the DB `translations` table.
- Translated usage notes and example translations stay in JSONL/compiled artifacts for now and are not yet surfaced in backend/admin APIs.
