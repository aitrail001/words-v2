# Lexicon Tool

Offline/admin lexicon pipeline for Words-Codex.

Quick operator references:
- `tools/lexicon/OPERATOR_GUIDE.md` — step-by-step setup and runbook for admins/operators
- `tools/lexicon/.env.example` — tool-local example env file for offline lexicon runs

Current scope:
- `python -m tools.lexicon.cli build-base ...` builds a bounded normalized base summary from seed words
- `python -m tools.lexicon.cli build-base ... --output-dir ...` writes normalized snapshot JSONL files
- `python -m tools.lexicon.cli enrich --snapshot-dir ...` generates learner-facing `enrichments.jsonl` for an existing snapshot
- `python -m tools.lexicon.cli validate --snapshot-dir ...` validates normalized snapshot JSONL files
- `python -m tools.lexicon.cli validate --compiled-input ...` validates compiled learner-facing JSONL rows (`--compiled-path` remains an alias)
- `python -m tools.lexicon.cli compile-export --snapshot-dir ... --output ...` compiles normalized snapshot files into `words.enriched.jsonl`
- `python -m tools.lexicon.cli import-db --input ... --dry-run` loads compiled rows and prints a local-admin import summary
- `python -m tools.lexicon.cli import-db --input ... --source-type ... --source-reference ... --language ...` runs the local import path against the configured DB

## Dependencies

Install tool-local dependencies separately from the backend runtime image:

```bash
python -m pip install -r tools/lexicon/requirements.txt
```

`build-base` is expected to fail loudly unless both of these are available:
- `nltk` with the WordNet corpus installed and readable
- `wordfreq`

This is intentional. The operator path should not silently fall back to fake lexical providers.

## Operator flow

Recommended offline flow:

```bash
python -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
python -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto
python -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
python -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
```

This separation keeps lexical base generation, learner-facing enrichment, validation, compilation, and DB import independently rerunnable.

## Usage

### Install offline tool dependencies

Runtime/admin dependencies only:

```bash
python3 -m pip install -r tools/lexicon/requirements.txt
python3 -m nltk.downloader wordnet omw-1.4
```

Local development and test runner dependencies:

```bash
python3 -m pip install -r tools/lexicon/requirements-dev.txt
python3 -m nltk.downloader wordnet omw-1.4
python3 -m pytest tools/lexicon/tests -q
```

If you use the repo-local lexicon virtualenv, the same flow is:

```bash
./.venv-lexicon/bin/python -m pip install -r tools/lexicon/requirements-dev.txt
./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

`build-base` now fails loudly if `nltk`/WordNet or `wordfreq` are unavailable.

For real endpoint-backed enrichment, set:
- `LEXICON_LLM_BASE_URL` — base URL for an OpenAI-compatible Responses API
- `LEXICON_LLM_MODEL` — model identifier for that endpoint
- `LEXICON_LLM_API_KEY` — API key or token for that endpoint
- `LEXICON_LLM_TRANSPORT` — optional transport hint; set `node` for Cloudflare-fronted gateways that reject the Python client

`LEXICON_LLM_PROVIDER` is still accepted as a backward-compatible alias for `LEXICON_LLM_BASE_URL`.

If you need the Node-backed gateway path, install the tool-local Node dependency too:

```bash
npm --prefix tools/lexicon ci
```

### Build base summary

```bash
python -m tools.lexicon.cli build-base run set lead
```

### Build and write normalized snapshot files

```bash
python -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
```

### Generate learner-facing enrichments

```bash
python -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto
```


### Tiny local OpenAI-compatible smoke

Use the helper command:

```bash
python -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-smoke run set
```

For Cloudflare-fronted custom gateways like `https://api.nwai.cc`, use the Node-backed mode:

```bash
LEXICON_LLM_TRANSPORT=node \
python -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-smoke run set
```

This is the fastest local check for a real endpoint. It should:
- use a tiny seed set like `run set`
- require `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, and `LEXICON_LLM_API_KEY`
- fail loudly if the endpoint returns malformed learner-facing payloads for required fields or schema-constrained fields like `definition`, `examples`, `confidence`, `cefr_level`, `register`, `forms`, or list fields
- write a temporary snapshot and compiled export you can inspect or delete after the run

### Validate a normalized snapshot

```bash
python -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
```

### Validate a compiled export

```bash
python -m tools.lexicon.cli validate --compiled-input data/lexicon/snapshots/demo/words.enriched.jsonl
```

### Compile export

```bash
python -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
```

### Import dry run

```bash
python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
```

### Import into local DB

```bash
python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --source-type lexicon_snapshot --source-reference demo-snapshot-20260307 --language en
```

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
python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --source-type lexicon_snapshot --source-reference demo-snapshot-20260307 --language en
```

If your usual local dev DB has unrelated schema drift, use an isolated temporary Postgres instance for the smoke instead of reusing that DB blindly.

Notes:
- `build-base` should use real WordNet and `wordfreq` providers on the operator path
- `enrich` remains an offline admin step and supports `--provider-mode auto|placeholder|openai_compatible|openai_compatible_node`
- use `openai_compatible_node` when a custom gateway works with the official Node OpenAI SDK but rejects the Python transport
- `.github/workflows/lexicon-openai-compatible-smoke.yml` is a manual/nightly secret-backed OpenAI-compatible smoke workflow that calls the configured endpoint using `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, `LEXICON_LLM_API_KEY`, and optional `LEXICON_LLM_TRANSPORT=node`
- non-dry-run import expects backend DB dependencies and settings to be available in the local environment
