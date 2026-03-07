# Lexicon Operator Guide

This guide is for the offline/admin lexicon pipeline that builds snapshot files, enriches them for learners, validates them, compiles a DB-ready JSONL export, and optionally imports that export into the local database.

## 1. What this tool is for

Use `tools/lexicon` when you want to:
- build a WordNet + `wordfreq` based lexical snapshot
- enrich learner-facing fields with an LLM in a separate admin step
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

## 4. Recommended operator flow

Build a normalized snapshot first:

```bash
python -m tools.lexicon.cli build-base run set lead --output-dir data/lexicon/snapshots/demo
```

Enrich the learner-facing layer:

```bash
python -m tools.lexicon.cli enrich --snapshot-dir data/lexicon/snapshots/demo --provider-mode auto
```

Validate the normalized snapshot plus enrichments:

```bash
python -m tools.lexicon.cli validate --snapshot-dir data/lexicon/snapshots/demo
```

Compile the final export:

```bash
python -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/demo --output data/lexicon/snapshots/demo/words.enriched.jsonl
```

Run an import dry-run summary:

```bash
python -m tools.lexicon.cli import-db --input data/lexicon/snapshots/demo/words.enriched.jsonl --dry-run
```

## 5. Provider modes

`enrich` supports these provider modes:
- `auto` — use `openai_compatible_node` when `LEXICON_LLM_TRANSPORT=node`, otherwise use the default endpoint path when LLM env is present, or placeholder mode when not
- `placeholder` — generate deterministic fake learner-facing data for local non-LLM testing
- `openai_compatible` — use the Python OpenAI-compatible Responses transport
- `openai_compatible_node` — use the official Node OpenAI SDK transport

## 6. Custom OpenAI-compatible gateways

If your gateway works with the official Node OpenAI SDK but rejects the Python transport, set:

```bash
export LEXICON_LLM_BASE_URL='https://api.nwai.cc'
export LEXICON_LLM_MODEL='gpt-5.1'
export LEXICON_LLM_API_KEY='your-local-key'
export LEXICON_LLM_TRANSPORT='node'
```

Then use either the normal `enrich` flow with `--provider-mode auto` or the bounded smoke command:

```bash
python -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-smoke run set
```

## 7. Import into the local DB

For a real non-dry-run import, your backend DB settings must be available in the shell:

```bash
python -m tools.lexicon.cli import-db \
  --input data/lexicon/snapshots/demo/words.enriched.jsonl \
  --source-type lexicon_snapshot \
  --source-reference demo-snapshot-20260307 \
  --language en
```

Use a clean local DB or isolated temporary Postgres instance if your main dev DB has unrelated schema drift.

## 8. Output files and linking

A single snapshot directory links together the pipeline stages:
- `lexemes.jsonl` holds lemma-level records
- `senses.jsonl` links back to lexemes by `lexeme_id`
- `enrichments.jsonl` links to senses by `sense_id`
- `words.enriched.jsonl` is the compiled learner-facing export used by `import-db`

Re-run any stage independently as long as the required upstream files already exist in that snapshot directory.

## 9. Common failure modes

- Missing WordNet or `wordfreq` dependencies: re-run `python3 -m pip install -r tools/lexicon/requirements.txt` and `python3 -m nltk.downloader wordnet omw-1.4`
- Missing LLM env for real enrichment: confirm `LEXICON_LLM_BASE_URL`, `LEXICON_LLM_MODEL`, and `LEXICON_LLM_API_KEY` are exported in the current shell
- Cloudflare/custom gateway rejects Python transport: install Node deps with `npm --prefix tools/lexicon ci`, then set `LEXICON_LLM_TRANSPORT=node`
- Import path fails against a drifted local DB: use a clean local DB or isolated temporary Postgres instance instead of forcing the import into a broken dev database

## 10. Operator evidence checklist

After a successful run, keep or inspect these artifacts:
- the snapshot directory containing `lexemes.jsonl`, `senses.jsonl`, and `enrichments.jsonl`
- the compiled export `words.enriched.jsonl`
- the exact command lines used for `build-base`, `enrich`, `validate`, `compile-export`, and optional `import-db`
- the summary counts printed by the CLI so you can compare later reruns and imports

## 11. See also

- `tools/lexicon/README.md`
- `tools/lexicon/.env.example`
- `.github/workflows/lexicon-openai-compatible-smoke.yml`
