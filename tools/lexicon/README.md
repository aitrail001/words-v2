# Lexicon Tool

Offline/admin lexicon pipeline for Words-Codex.

Quick operator references:
- `tools/lexicon/OPERATOR_GUIDE.md` — step-by-step setup and runbook for admins/operators
- `tools/lexicon/.env.example` — tool-local example env file for offline lexicon runs
- `tools/lexicon/SELECTION_RUBRIC.md` — learner-priority rubric used to judge selector and rerank quality

Current scope:
- `python3 -m tools.lexicon.cli build-base ...` builds a bounded normalized base summary from explicit seed words
- `python3 -m tools.lexicon.cli build-base --top-words N ...` builds a filtered top-common-word inventory from `wordfreq`
- `python3 -m tools.lexicon.cli build-base --rollout-stage 100|1000|5000|30000 ...` runs the staged common-word rollout aliases
- `python3 -m tools.lexicon.cli build-base ... --output-dir ...` writes normalized snapshot JSONL files with shared entry metadata (`entry_id`, `entry_type`, `normalized_form`, `source_provenance`) plus canonical registry sidecars (`canonical_entries.jsonl`, `canonical_variants.jsonl`, `generation_status.jsonl`)
- `python3 -m tools.lexicon.cli enrich --snapshot-dir ...` generates learner-facing `enrichments.jsonl` for an existing snapshot, including required learner translations for `zh-Hans`, `es`, `ar`, `pt-BR`, and `ja`
- `python3 -m tools.lexicon.cli enrich --snapshot-dir ... --mode per_word --max-concurrency ...` enriches one lexeme per LLM call, lets the model choose the learner-friendly subset of grounded meanings, repeats the hard meaning cap in the prompt, and performs one repair retry when a word-level payload is invalid
- `python3 -m tools.lexicon.cli enrich --snapshot-dir ... --mode per_word --resume --checkpoint-path ... --failures-output ...` now writes incremental `enrichments.jsonl`, `enrich.checkpoint.jsonl`, and `enrich.failures.jsonl` artifacts so large 1K -> 5K -> 30K runs can resume safely after partial failure
- `python3 -m tools.lexicon.cli rerank-senses --snapshot-dir ...` writes grounded LLM rerank decisions for existing snapshots
- `python3 -m tools.lexicon.cli compare-selection --snapshot-dir ... --rerank-file ...` compares deterministic selection against reranked selection
- `python3 -m tools.lexicon.cli benchmark-selection --output-dir ...` runs built-in tuning/holdout benchmark snapshots with optional rerank comparisons
- `python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir ...` scores deterministic selections and writes `selection_decisions.jsonl`
- `python3 -m tools.lexicon.cli prepare-review --snapshot-dir ... --decisions ...` reranks only risky lexemes and writes reviewed decisions plus optional `review_queue.jsonl`
- `python3 -m tools.lexicon.cli detect-ambiguous-forms --output ... <words...>` emits only the bounded canonicalization tail that needs optional LLM/operator adjudication
- unresolved ambiguous-form tails are now deferred from `lexemes.jsonl` / `senses.jsonl` until adjudication, while core headwords still build normally and remain deterministic-first
- `python3 -m tools.lexicon.cli adjudicate-forms --input ambiguous_forms.jsonl --output form_adjudications.jsonl ...` runs bounded adjudication that may only choose the surface form or one of the deterministic candidate forms
- `python3 -m tools.lexicon.cli lookup-entry --snapshot-dir ... <word>` resolves a surface form to the canonical entry chosen for this snapshot
- `python3 -m tools.lexicon.cli status-entry --snapshot-dir ... [--check-db] <word>` reports canonical/build/enrich/compile status and can optionally confirm DB presence
- `python3 -m tools.lexicon.cli validate --snapshot-dir ...` validates normalized snapshot JSONL files
- `python3 -m tools.lexicon.cli validate --compiled-input ...` validates compiled learner-facing JSONL rows (`--compiled-path` remains an alias)
- `python3 -m tools.lexicon.cli compile-export --snapshot-dir ... --output ...` compiles normalized snapshot files into `words.enriched.jsonl`, preserving sense-level enrichment provenance and translated sense payloads needed for DB/artifact writeback
- `python3 -m tools.lexicon.cli compile-export --snapshot-dir ... --decisions ... --decision-filter mode_c_safe --output ...` compiles only deterministic-safe or auto-accepted lexemes from `selection_decisions.jsonl`
- filtered compile runs require both `--decisions` and `--decision-filter`; passing one without the other now fails loudly
- `python3 -m tools.lexicon.cli import-db --input ... --dry-run` loads compiled rows and prints a local-admin import summary, including learner-facing example/relation and enrichment provenance counts
- `python3 -m tools.lexicon.cli import-db --input ... --source-type ... --source-reference ... --language ...` runs the local import path against the configured DB, writing `words`, `meanings`, meaning-level `translations`, `meaning_examples`, `word_relations`, and enrichment job/run metadata while safely replacing prior examples/relations and collapsing shared per-word `generation_run_id` groups to one enrichment run row

## Dependencies

Install tool-local dependencies separately from the backend runtime image:

```bash
python -m pip install -r tools/lexicon/requirements.txt
```

`build-base` is expected to fail loudly unless both of these are available:
- `nltk` with the WordNet corpus installed and readable
- `wordfreq`

This is intentional. The operator path should not silently fall back to fake lexical providers.

## Canonical final DB write path

For generated learner-facing lexicon content, the canonical final DB write path is:

1. `build-base`
2. optional ambiguous-form adjudication flow (`detect-ambiguous-forms` / `adjudicate-forms` / rerun `build-base --adjudications ...`)
3. optional review-prep flow (`score-selection-risk` / `prepare-review`)
4. `enrich`
5. `validate --snapshot-dir`
6. `compile-export`
7. `validate --compiled-input`
8. `import-db`

Use staged review as the decision/review layer, not as a competing final learner-enrichment publisher.
Today, `import-db` is the only path that lands the richer learner-facing writeback (`meaning_examples`, `word_relations`, enrichment jobs/runs, phonetic provenance) into the local DB.
The application still uses one Postgres database/server, but lexicon-owned tables now live in the dedicated `lexicon` schema so reference data is separated from runtime/app tables.

Ambiguous-form adjudication is intentionally narrow:
- it is optional and off the default path
- it only touches surface forms that deterministic canonicalization marked as `unknown_needs_llm`
- it may only keep the surface form or choose from bounded `candidate_forms` already emitted by the deterministic pass
- it persists replayable artifacts as `ambiguous_forms.jsonl` and `form_adjudications.jsonl`

See `docs/decisions/ADR-004-lexicon-canonical-final-ingestion-path.md` and `docs/runbooks/lexicon-working-gate.md`.

## Operator flow

Recommended offline flow:

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-base --top-words 1000 --output-dir data/lexicon/snapshots/words-1000
python3 -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
# build-base now deterministically collapses obvious inflectional duplicates like things->thing and gives->give while keeping lexicalized forms like left as separate entries linked to their base family
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode placeholder
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
python3 -m tools.lexicon.cli lookup-entry --snapshot-dir data/lexicon/snapshots/demo things
python3 -m tools.lexicon.cli status-entry --snapshot-dir data/lexicon/snapshots/demo --check-db thing
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4
# per_word prompts use WordNet as grounding context, repeat the hard 8/6/4 meaning cap, require a JSON object only, and retry once with a repair prompt if the first payload is invalid
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --mode per_word --max-concurrency 4 --model gpt-5.4 --reasoning-effort low
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/words-1000 --provider-mode auto --mode per_word --max-concurrency 4 --request-delay-seconds 1.0 --max-failures 25
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/words-1000 --provider-mode auto --mode per_word --max-concurrency 4 --request-delay-seconds 1.0 --max-failures 25 --resume
# per_word large runs append completed lexemes directly into enrichments.jsonl and keep sidecar checkpoint/failure ledgers in the snapshot directory by default
python3 -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --decision-filter mode_c_safe --output data/lexicon/snapshots/demo/words.mode-c-safe.enriched.jsonl
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
python3 -m tools.lexicon.cli rerank-senses --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --candidate-source candidates --candidate-limit 8
python3 -m tools.lexicon.cli compare-selection --snapshot-dir data/lexicon/snapshots/demo --rerank-file data/lexicon/snapshots/demo/sense_reranks.jsonl
python3 -m tools.lexicon.cli benchmark-selection --output-dir /tmp/lexicon-benchmark --dataset tuning --dataset holdout --with-rerank --provider-mode auto --candidate-source selected_only --candidate-source candidates --candidate-source full_wordnet
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

This separation keeps lexical base generation, learner-facing enrichment, validation, compilation, and DB import independently rerunnable.

For staged review runs, `selection_decisions.jsonl` can now feed two downstream paths:
- import into the admin review portal for human review and overrides
- filtered `compile-export --decision-filter mode_c_safe` runs for direct import of safe lexemes only

## Usage

### Install offline tool dependencies

Runtime/admin dependencies only:

```bash
python3.13 -m venv .venv-lexicon
./.venv-lexicon/bin/python -m pip install -r tools/lexicon/requirements.txt
./.venv-lexicon/bin/python -m nltk.downloader wordnet omw-1.4
```

Local development and test runner dependencies:

```bash
python3.13 -m venv .venv-lexicon
./.venv-lexicon/bin/python -m pip install -r tools/lexicon/requirements-dev.txt
./.venv-lexicon/bin/python -m nltk.downloader wordnet omw-1.4
./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

Repo-local env policy:

- keep the durable lexicon env at repo root as `./.venv-lexicon`
- keep the durable backend env at repo root as `./.venv-backend`
- recreate those stable envs when dependencies/runtime change
- avoid keeping durable virtualenvs inside disposable git worktrees

`build-base` now fails loudly if `nltk`/WordNet or `wordfreq` are unavailable.

For real endpoint-backed enrichment, set:
- `LEXICON_LLM_BASE_URL` — base URL for an OpenAI-compatible Responses API
- `LEXICON_LLM_MODEL` — model identifier for that endpoint
- `LEXICON_LLM_API_KEY` — API key or token for that endpoint
- `LEXICON_LLM_REASONING_EFFORT` — optional reasoning control for compatible Responses APIs (`low`, `medium`, `high`)
- `LEXICON_LLM_TRANSPORT` — optional transport hint; set `node` for Cloudflare-fronted gateways that reject the Python client

`LEXICON_LLM_PROVIDER` is still accepted as a backward-compatible alias for `LEXICON_LLM_BASE_URL`.

If you need the Node-backed gateway path, install the tool-local Node dependency too:

```bash
npm --prefix tools/lexicon ci
```

### Build base summary

```bash
python3 -m tools.lexicon.cli build-base run set lead
```

### Build and write normalized snapshot files

```bash
python3 -m tools.lexicon.cli build-base --rollout-stage 100 --output-dir data/lexicon/snapshots/words-100
python3 -m tools.lexicon.cli build-base --top-words 1000 --output-dir data/lexicon/snapshots/words-1000
python3 -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
# build-base now deterministically collapses obvious inflectional duplicates like things->thing and gives->give while keeping lexicalized forms like left as separate entries linked to their base family
python3 -m tools.lexicon.cli detect-ambiguous-forms --output data/lexicon/snapshots/demo/ambiguous_forms.jsonl close light play
python3 -m tools.lexicon.cli adjudicate-forms --input data/lexicon/snapshots/demo/ambiguous_forms.jsonl --output data/lexicon/snapshots/demo/form_adjudications.jsonl --provider-mode placeholder
python3 -m tools.lexicon.cli build-base close light play --adjudications data/lexicon/snapshots/demo/form_adjudications.jsonl --output-dir data/lexicon/snapshots/demo-adjudicated
python3 -m tools.lexicon.cli lookup-entry --snapshot-dir data/lexicon/snapshots/demo things
python3 -m tools.lexicon.cli status-entry --snapshot-dir data/lexicon/snapshots/demo --check-db thing
```

### Generate learner-facing enrichments

```bash
python3 -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto
```


### Tiny local OpenAI-compatible smoke

Use the helper command. It is now bounded by default to keep smoke runs fast: `1` word and `2` senses per word unless you override them.

```bash
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke run
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke --max-words 2 --max-senses 2 run set
python3 -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke --model gpt-5.4 --reasoning-effort low run
```

For Cloudflare-fronted custom gateways like `https://api.nwai.cc`, use the Node-backed mode:

```bash
LEXICON_LLM_TRANSPORT=node \
python3 -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-smoke run set
```

This is the fastest local check for a real endpoint. It should:
- default to a tiny bounded seed set like `run` unless you explicitly increase `--max-words`
- require `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, and `LEXICON_LLM_API_KEY`
- fail loudly if the endpoint returns malformed learner-facing payloads for required fields or schema-constrained fields like `definition`, `examples`, `confidence`, `cefr_level`, `register`, `forms`, or list fields
- write a temporary snapshot and compiled export you can inspect or delete after the run

### Grounded LLM rerank

Use the optional rerank stage when you want the LLM to choose among grounded WordNet candidates without inventing new senses:

```bash
python3 -m tools.lexicon.cli rerank-senses --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --candidate-source candidates --candidate-limit 8
python3 -m tools.lexicon.cli compare-selection --snapshot-dir data/lexicon/snapshots/demo --rerank-file data/lexicon/snapshots/demo/sense_reranks.jsonl
python3 -m tools.lexicon.cli benchmark-selection --output-dir /tmp/lexicon-benchmark --dataset tuning --dataset holdout --with-rerank --provider-mode auto --candidate-source selected_only --candidate-source candidates --candidate-source full_wordnet
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

`rerank-senses` only returns ordered `wn_synset_id` choices from the provided candidates. It does not generate learner-facing definitions and it does not invent senses.

Candidate-source modes:
- `selected_only` reorders only the senses already selected in the snapshot and is the safest audit mode.
- `candidates` reranks a bounded ranked WordNet shortlist and is the recommended comparison mode.
- `full_wordnet` reranks the full ranked WordNet pool for the lemma and is best treated as an exploratory evaluation mode because it is slower and more aggressive.

### Risk scoring and review prep

Use these commands when you want the offline tool to move from deterministic selection into targeted rerank and human-review staging instead of inspecting raw JSONL by hand:

```bash
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

This gives you a practical three-step operator flow:
- deterministic snapshot selection from `build-base`
- LLM rerank only for words whose `risk_band` is not `deterministic_only`
- explicit human review queue via `review_required=true` rows in `review_queue.jsonl`

Key outputs:
- `selection_decisions.jsonl` stores the deterministic choice, risk score, risk band, candidate metadata, and rerank outcome fields
- `review_queue.jsonl` contains only lexemes still requiring human review after bounded rerank
- `auto_accepted=true` means rerank was applied and accepted without human review; `review_required=true` means keep it staged for review

### Validate a normalized snapshot

```bash
python3 -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
```

### Validate a compiled export

```bash
python3 -m tools.lexicon.cli validate --compiled-input data/lexicon/snapshots/demo/words.enriched.jsonl
```

### Compile export

```bash
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
```

### Import dry run

```bash
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
python3 -m tools.lexicon.cli rerank-senses --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto --candidate-source candidates --candidate-limit 8
python3 -m tools.lexicon.cli compare-selection --snapshot-dir data/lexicon/snapshots/demo --rerank-file data/lexicon/snapshots/demo/sense_reranks.jsonl
python3 -m tools.lexicon.cli benchmark-selection --output-dir /tmp/lexicon-benchmark --dataset tuning --dataset holdout --with-rerank --provider-mode auto --candidate-source selected_only --candidate-source candidates --candidate-source full_wordnet
python3 -m tools.lexicon.cli score-selection-risk --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/selection_decisions.jsonl
python3 -m tools.lexicon.cli prepare-review --snapshot-dir data/lexicon/snapshots/demo --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl --provider-mode auto --candidate-source candidates --candidate-limit 8
```

### Import into local DB

```bash
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --source-type lexicon_snapshot --source-reference demo-snapshot-20260307 --language en
```

This import still uses the normal backend DB connection settings, but the lexicon records are persisted under the dedicated Postgres `lexicon` schema while runtime/app tables remain outside that schema.

### Real local DB import smoke

For a true non-dry-run smoke, point the backend settings at a clean local Postgres DB, run migrations, then import a compiled file:

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://vocabapp:devpassword@localhost:5432/vocabapp_dev \
DATABASE_URL_SYNC=postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev \
../.venv-lexicon/bin/alembic upgrade head

cd ..
DATABASE_URL=postgresql+asyncpg://vocabapp:devpassword@localhost:5432/vocabapp_dev \
DATABASE_URL_SYNC=postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev \
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --source-type lexicon_snapshot --source-reference demo-snapshot-20260307 --language en
```

If your usual local dev DB has unrelated schema drift, use an isolated temporary Postgres instance for the smoke instead of reusing that DB blindly.

Notes:
- `build-base` should use real WordNet and `wordfreq` providers on the operator path
- `build-base` now uses learner-oriented, frequency-aware sense ranking with adaptive `4/6/8` selection inside the `--max-senses` ceiling; WordNet lemma counts, gloss heuristics, canonical-label affinity, and a soft adjective/adverb viability layer help useful mixed-POS senses compete without hard POS quotas, and the default ceiling is `8`
- selector and rerank quality should be judged with `tools/lexicon/SELECTION_RUBRIC.md`
- `enrich` remains an offline admin step and supports `--provider-mode auto|placeholder|openai_compatible|openai_compatible_node`
- use `openai_compatible_node` when a custom gateway works with the official Node OpenAI SDK but rejects the Python transport
- `.github/workflows/lexicon-openai-compatible-smoke.yml` is a manual/nightly secret-backed OpenAI-compatible smoke workflow that calls the configured endpoint using `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, `LEXICON_LLM_API_KEY`, and optional `LEXICON_LLM_TRANSPORT=node`
- Configure those values in the GitHub environment `lexicon-llm` (environment vars for base URL/model/transport, environment secret for API key); local `.env` files are not read by GitHub Actions.
- If the workflow returns Cloudflare challenge HTML/403, the runner reached the gateway but was blocked upstream; first try `LEXICON_LLM_TRANSPORT=node`, then move to a self-hosted runner or gateway allow/bypass rules if GitHub-hosted runners are still challenged.
- model benchmark conclusions and artifact notes for `gpt-5.1`/`gpt-5.2`/`gpt-5.3`/`gpt-5.4` live in `tools/lexicon/MODEL_BENCHMARKS.md`
- non-dry-run import expects backend DB dependencies and settings to be available in the local environment


Translation note:
- PR 2 stores translated definitions in the DB `translations` table during `import-db`.
- Translated usage notes and example translations remain in lexicon JSONL artifacts / compiled sense payloads for now; they are not yet exposed through backend/admin APIs in this slice.
