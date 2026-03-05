# ADR-002: Branch Governance

## Context

This repository uses GitHub branch governance to block regressions before merge.
We now have required PR checks and an additional full E2E run on `main`.

## Decision

1. Use **Rulesets as the single source of truth** for `main` branch merge controls.
2. Do not duplicate equivalent controls in classic Branch Protection unless there is a temporary migration need.
3. Keep required PR checks aligned to the exact check context names emitted by CI.

## Required PR Checks

At minimum, require these check contexts on pull requests to `main`:

1. `CI / Backend (lint + test) (pull_request)`
2. `CI / Frontend (lint + test) (pull_request)`
3. `CI / E2E Smoke (required) (pull_request)`

`CI / E2E Full` is expected to run on `main` push/workflow dispatch and is not required on PR.

## Consequences

1. Using both rulesets and classic protection for the same controls can cause:
   - conflicting required checks and merge blockers
   - operator confusion when one system is updated and the other is stale
   - harder incident triage when merges are blocked unexpectedly

2. Operators must keep required check names synchronized with CI job/context names.

## Operational Checklist

### Workflow/Check Name Changes
When workflow names, job names, or trigger contexts change:

1. Merge workflow changes.
2. Run CI at least once so GitHub registers updated check contexts.
3. Open `Settings -> Rules -> Rulesets -> main` and refresh required status checks to the new exact names.
4. Remove stale check entries that are no longer emitted.
5. Validate on a live PR that all required checks appear and enforce correctly.
6. Confirm `main` push still runs `CI / E2E Full`.

### Review Cadence

Re-verify this policy whenever:

1. CI workflow structure changes (`.github/workflows/ci.yml`).
2. Branch governance settings are modified.
3. A merge is blocked by an unexpected required check mismatch.

## Status

ACCEPTED (2026-03-05)
