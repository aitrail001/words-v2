# Rollback Runbook

Use this runbook when a release candidate causes user-visible regression or service risk in pre-prod or production.

## Trigger conditions

Start rollback when any of the following is true:

- API health fails or sustained 5xx rate exceeds acceptable limits
- login, review, import, or key admin/operator flows fail after release
- a migration introduces blocking correctness or performance risk
- data integrity risk is detected
- the incident owner declares rollback the fastest safe path

## Inputs you need

Before executing rollback, identify:

- the bad candidate SHA / tag
- the last known good release
- the current environment
- whether a migration rollback is safe, required, or prohibited
- who is coordinating communications and verification

## Rollback flow

1. Stop further promotion activity.
2. Identify the last known good artifact.
3. Execute the environment’s rollback command or workflow.
4. Verify service health.
5. Verify core smoke paths.
6. Decide whether DB state also requires intervention.
7. Record what was rolled back, why, and what still needs follow-up.

## Database caution

Application rollback and database rollback are not always the same operation.

Rules:
- never assume migrations are safely reversible without checking
- if rollback keeps the newer DB schema, verify app compatibility with that schema
- if data repair is required, document it separately from the app rollback itself

## Minimum post-rollback checks

After rollback:

- API health is green
- learner login works
- learner review entry works for at least a smoke case
- import path is healthy if it was in scope
- admin frontend and critical admin/operator flows work if they were in scope

## Records to keep

Capture:

- incident or release reference
- rollback command or workflow URL
- health-check evidence
- smoke verification evidence
- any DB-specific follow-up required

## Related docs

- `release-promotion.md`
- `real-preprod-verification.md`
- `preprod-readiness-checklist.md`
