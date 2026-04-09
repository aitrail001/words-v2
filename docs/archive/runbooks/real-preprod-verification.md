# Real Pre-Prod Verification

Use this runbook when a release candidate must be validated against the actual deployed pre-prod environment and its persistent populated database. Run this after `Deploy Preprod` succeeds and before `Production Promote`.

For the disposable GitHub Actions rehearsal, see [`preprod-readiness-checklist.md`](./preprod-readiness-checklist.md).

## Scope

This runbook is for the **real pre-prod environment**:

- persistent deployed API/frontend/worker services
- persistent pre-prod Postgres and Redis
- existing application and lexicon data already present
- real migration and rollback evidence against that environment

It is not the Docker-based rehearsal that creates and destroys an ephemeral local stack.

## Preconditions

Before running real pre-prod verification:

- release candidate SHA is frozen
- pre-prod URLs are known
- operator has deploy access
- operator has DB migration access
- rollback procedure is ready
- data owners understand that pre-prod already contains persistent data

## Required evidence

Capture and keep:

- deploy command or workflow run URL
- migration command output against pre-prod DB
- rollback drill output if required by the release window
- post-deploy health checks
- smoke verification output
- any bounded lexicon smoke artifacts and `source_reference` used

## Verification flow

1. Deploy the candidate to pre-prod.
2. Run health checks against the deployed API and frontend.
3. Apply DB migrations against the existing pre-prod DB.
4. Run rollback drill if the release window requires it.
5. Re-apply the candidate if rollback was exercised.
6. Run app smoke checks against the deployed environment.
7. If lexicon/import behavior is in scope, run a tiny bounded lexicon smoke against the persistent pre-prod DB.

## Persistent DB rules

Because pre-prod already contains data:

- do not replace the database with a fresh Docker database for final verification
- do not run bulk lexicon imports as part of release verification
- use isolated, auditable smoke data only
- prefer unique source references for any lexicon smoke import

Recommended lexicon smoke characteristics:

- 1-3 words only
- unique `source_reference` such as `preprod-lexicon-smoke-<date>-<sha>`
- verify readback via `GET /api/words/{word_id}/enrichment`
- record cleanup expectations if the smoke data should later be removed

## Lexicon-specific check

Run this only when the release touches lexicon import/schema/API paths or when you need confidence that the admin lexicon path still works in pre-prod.

Minimum lexicon check:

1. generate or provide a tiny validated compiled JSONL
2. import it with a unique `source_reference`
3. authenticate against pre-prod
4. search an imported word
5. verify `GET /api/words/{word_id}/enrichment` returns learner-facing fields

## Pass criteria

Real pre-prod verification passes only if all are true:

- deploy succeeded
- migrations completed without manual repair
- rollback expectations were satisfied for the release window
- health and smoke checks passed against the deployed pre-prod environment
- any lexicon smoke run passed and returned expected enrichment data

## Related docs

- [`preprod-readiness-checklist.md`](./preprod-readiness-checklist.md)
- [`release-promotion.md`](./release-promotion.md)
- [`rollback.md`](./rollback.md)
- [`lexicon-working-gate.md`](./lexicon-working-gate.md)
