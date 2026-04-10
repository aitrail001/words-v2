# tools/lexicon agent guide

## Runtime
- Run lexicon CLI commands with `.venv-lexicon/bin/python`, not `.venv-backend/bin/python`.
- Bootstrap a fresh worktree with `make worktree-bootstrap`. If you only need lexicon tooling, `make lexicon-install` is sufficient.
- `tools/lexicon/.env.local` is the canonical local endpoint config for real lexicon LLM runs.

## Canonical commands
- `make lexicon-enrich-core LEXICON_ARGS='--snapshot-dir /abs/path/to/snapshot --resume'`
- `make lexicon-enrich-translations LEXICON_ARGS='--snapshot-dir /abs/path/to/snapshot --resume'`
- `make lexicon-merge LEXICON_ARGS='--core-input /abs/path/core.jsonl --translations-input /abs/path/translations.jsonl --output /abs/path/words.enriched.jsonl'`
- `make lexicon-smoke-real LEXICON_ARGS='--snapshot-dir /abs/path/to/snapshot --max-concurrency 1 --max-failures 1'`

## Guardrails
- Prefer the make targets above so the interpreter and `.env.local` loading stay consistent.
- The CLI now fails fast when it is not running under `.venv-lexicon`.
- If a test or one-off debug session must bypass that check, set `LEXICON_SKIP_VENV_GUARD=1` explicitly for that invocation.
- After addressing inline PR review feedback for lexicon changes, reply and resolve the GitHub review thread with `make gh-resolve-review-thread GH_ARGS='--pr <pr> --comment-id <id> --body-file <path>'` or `--body '...'`.
