# Real Pre-Prod Verification

Use this runbook when a release candidate must be validated against the actual deployed pre-prod environment and its persistent populated database.

Run this after `Deploy Preprod` succeeds and before `Production Promote`.

For the disposable rehearsal, see `preprod-readiness-checklist.md`.

## Scope

This runbook is for the real pre-prod environment:

- deployed API, worker, learner frontend, and admin frontend services
- persistent pre-prod Postgres and Redis
- existing application and lexicon data already present
- real migrations and real rollback expectations

It is not the disposable Docker rehearsal.

## Preconditions

Before running real pre-prod verification:

- release candidate SHA or tag is frozen
- pre-prod URLs are known
- operator has deploy access
- migration access is available
- rollback procedure is ready
- release owners know whether lexicon behavior is in scope

## Required evidence

Capture and keep:

- deploy command or workflow run URL
- migration output against the real pre-prod DB
- health-check results
- smoke verification results
- rollback drill evidence if the release window requires one
- any bounded lexicon smoke evidence if lexicon/import paths are in scope

## Verification flow

1. Deploy the candidate to pre-prod.
2. Verify service health for API, learner frontend, and admin frontend.
3. Apply DB migrations against the existing pre-prod DB.
4. Run bounded smoke checks against the deployed environment.
5. If required for the release window, perform the rollback drill.
6. Re-deploy the candidate if rollback was exercised.
7. Record final pass/fail evidence.

## Persistent data rules

Because pre-prod contains persistent data:

- do not replace the DB with a fresh disposable DB
- do not run broad bulk imports as part of release verification
- use only isolated, auditable smoke data
- use unique identifiers for any temporary lexicon smoke material

## Optional lexicon-specific check

Run this only when the release touches lexicon import/schema/API/operator paths or when the release manager explicitly wants lexicon confidence.

Recommended characteristics:

- tiny bounded input only
- unique `source_reference`
- verify readback through current APIs or admin/operator paths
- do not treat historical `compile-export` flows as the current source of truth

For the current lexicon operator contract, use `../../tools/lexicon/README.md`.

## Pass criteria

Real pre-prod verification passes only if all are true:

- deploy succeeded
- migrations completed without manual repair
- health checks passed
- required smoke checks passed
- rollback expectations for the release window were satisfied
- any lexicon-specific smoke in scope passed

## Related docs

- `preprod-readiness-checklist.md`
- `release-promotion.md`
- `rollback.md`
- `../../tools/lexicon/README.md`
