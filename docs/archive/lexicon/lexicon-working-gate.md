# Lexicon Working Gate v1

This runbook defines the minimum pass/fail gate for treating the lexicon tool as a working local-DB admin tool.

## Scope

This is a **working gate**, not a production-hardening gate.

It proves that an operator can:
- generate a bounded snapshot
- enrich it
- validate it
- compile it
- import it into a clean local DB
- inspect the imported learner-facing result through the backend API

## Canonical path

Use this path for final DB writes:

1. `build-base`
2. optional review-prep flow
3. `enrich`
4. `validate --snapshot-dir`
5. `compile-export`
6. `validate --compiled-input`
7. `import-db`

Do not treat staged review publish as the canonical final learner-enrichment write path.

## Preflight

Before running the gate:
- backend stack is clean and reachable
- Postgres DB is clean or isolated for the smoke
- lexicon Python environment is installed
- WordNet corpora are installed
- chosen enrichment mode is clear (`placeholder` or real endpoint)
- backend migrations are applied

## Required commands

Example bounded closure smoke:

```bash
python3 -m tools.lexicon.cli build-base run set lead --output-dir /tmp/lexicon-working-gate
python3 -m tools.lexicon.cli enrich --snapshot-dir /tmp/lexicon-working-gate --provider-mode placeholder
python3 -m tools.lexicon.cli validate --snapshot-dir /tmp/lexicon-working-gate
python3 -m tools.lexicon.cli compile-export --snapshot-dir /tmp/lexicon-working-gate --output /tmp/lexicon-working-gate/words.enriched.jsonl
python3 -m tools.lexicon.cli validate --compiled-input /tmp/lexicon-working-gate/words.enriched.jsonl
python3 -m tools.lexicon.cli import-db --input /tmp/lexicon-working-gate/words.enriched.jsonl --source-type lexicon_snapshot --source-reference lexicon-working-gate-20260308 --language en
```

Then inspect via backend API:
- authenticate
- search or look up one imported word
- call `GET /api/words/{word_id}/enrichment`

## Pass criteria

The gate passes only if all of these are true:
- `build-base` succeeds
- `enrich` succeeds
- `validate --snapshot-dir` reports zero errors
- `validate --compiled-input` reports zero errors
- `import-db` succeeds against a clean DB
- backend API returns imported meanings plus learner-facing enrichment for at least one imported word
- run evidence is recorded in `docs/status/project-status.md`

## Fail conditions

The gate fails if any of these happen:
- missing WordNet / `wordfreq` dependency fallback is silently used
- validation is skipped or returns errors
- import succeeds only partially or cannot be inspected via API
- imported enrichment is missing from DB/API for the tested word
- operator cannot reproduce the run from recorded commands/artifacts

## Evidence to keep

Keep these artifacts:
- snapshot directory
- compiled export file
- exact commands run
- import summary output
- API inspection output for at least one word
- status-board entry with date and command evidence

## Deferred beyond working gate

These do not block closure of the tool as working:
- admin frontend review UI
- explicit admin-only RBAC for enrichment inspection
- phrase/idiom linking and phrase tables
- automated live Postgres import smoke in CI
- stricter review-status gating before compile/import
- stronger compiled-schema validation
- batch reliability/budget controls for very large runs
