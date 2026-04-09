# Pre-Prod Readiness Checklist

Use this checklist before promoting a release candidate into a pre-prod test window.

This runbook covers the disposable rehearsal workflow in `.github/workflows/preprod-readiness.yml`. It is not a substitute for verifying the real deployed pre-prod environment.

For real environment verification, use `real-preprod-verification.md`.

## Purpose

The rehearsal answers:

- can the stack boot from current repo configuration?
- can migrations and smoke checks run in a disposable environment?
- can the dual-frontend stack (learner + admin) be exercised by automation?
- is rollback still documented and plausible before using the real environment?

## Preconditions

Before running the rehearsal:

- the release candidate SHA or tag is identified
- required CI on `main` is green for the candidate
- Docker-based stack boot is expected to work from the repo
- relevant environment variables or defaults for the rehearsal are available

## What the rehearsal should cover

Minimum expectations:

1. backend service boots
2. learner frontend boots
3. admin frontend boots
4. database and worker services boot
5. migrations apply cleanly in the disposable environment
6. required smoke paths can run against the disposable stack
7. rollback documentation still matches the current release flow

## Required evidence

Capture:

- workflow run URL or equivalent invocation evidence
- migration success evidence
- health-check evidence
- smoke verification evidence
- any failures and the exact fix applied before rerun

Put long command output in `docs/reports/` or the PR, not in `docs/status/project-status.md`.

## Pass criteria

The rehearsal passes only if all are true:

- workflow configuration is valid
- the disposable stack boots cleanly
- migrations succeed
- learner and admin smoke checks succeed
- no blocker remains for running real pre-prod verification next

## Does not prove

This rehearsal does **not** prove:

- real deploy wiring is configured for a real environment
- production promote variables are correct
- persistent pre-prod data behaves correctly
- rollback has been validated against the actual pre-prod environment

## Related docs

- `real-preprod-verification.md`
- `release-promotion.md`
- `rollback.md`
