# Release Promotion Runbook

Use this runbook to promote a release candidate from `main` to pre-prod and then production.

## Promotion model

The intended order is:

1. merge to `main`
2. required CI passes
3. create or identify the release candidate SHA / tag
4. run pre-prod readiness rehearsal
5. deploy to real pre-prod
6. complete real pre-prod verification
7. promote to production
8. monitor and rollback if needed

## Required repository/workflow inputs

The repo currently contains these workflow entry points:

- `.github/workflows/ci.yml`
- `.github/workflows/preprod-readiness.yml`
- `.github/workflows/deploy-preprod.yml`
- `.github/workflows/promote-prod.yml`

Real promotion still depends on environment-specific variables and commands that may not yet be wired for all environments.

## Repository variables

Keep the release workflow variables aligned with the current environment:

- `PREPROD_DEPLOY_COMMAND`
- `PROD_PROMOTE_COMMAND`
- `PREPROD_API_URL`
- `PREPROD_WEB_URL`
- `PROD_API_URL`
- `PROD_WEB_URL`

If the admin frontend has a distinct externally relevant URL in your environment, document and verify it alongside the learner frontend during release execution.

## Promotion checklist

### Before deploy-preprod
- required CI is green
- target SHA/tag is frozen
- rehearsal has passed or a justified exception is recorded
- rollback plan is ready

### Deploy pre-prod
- trigger `deploy-preprod.yml`
- record workflow run URL
- verify the intended artifact or SHA was deployed

### Verify real pre-prod
- follow `real-preprod-verification.md`
- do not skip persistent-environment checks just because rehearsal passed

### Promote production
- only promote after real pre-prod verification passes
- trigger `promote-prod.yml`
- record workflow run URL
- monitor health and key user flows immediately after promotion

## Stop conditions

Do not continue promotion if any of these are true:

- required CI is red
- deploy-preprod failed
- migrations failed in pre-prod
- core health checks failed
- smoke flows failed
- rollback path is unclear for the candidate

## Records to keep

For each release candidate, keep:

- commit SHA / tag
- rehearsal evidence
- deploy-preprod evidence
- real pre-prod verification evidence
- promote-prod evidence
- any rollback evidence

Store long-form evidence in `docs/reports/` or the PR/release record, not in the status board.

## Related docs

- `preprod-readiness-checklist.md`
- `real-preprod-verification.md`
- `rollback.md`
