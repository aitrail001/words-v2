# E2E Admin/User Split Design

## Goal

Split the current monolithic required Playwright full gate into separate admin and user full lanes while preserving a tiny required smoke gate that fails fast before the broader suites run.

## Current State

- GitHub CI currently defines:
  - `E2E Smoke (required)`
  - `E2E Full (required)`
- `E2E Full` depends on `E2E Smoke`.
- `E2E Full` starts a fresh Docker stack, waits for backend + both frontends, applies migrations, and runs `npm run test:full`.
- `test:full` is currently `playwright test`, with only two specs in `e2e/tests/full`, both effectively user-facing.
- Admin flows are mostly exercised through smoke specs rather than a dedicated full admin lane.

## Desired Outcome

Required CI gates should become:

- `E2E Smoke`
- `E2E Admin`
- `E2E User`

And the sequencing should be:

- `E2E Admin` depends on `E2E Smoke`
- `E2E User` depends on `E2E Smoke`

This keeps a tiny fail-fast gate in front of the broader suites while separating the full regression coverage by product surface.

## Scope

This change includes:

- splitting CI jobs in `.github/workflows/ci.yml`
- renaming E2E specs so ownership is explicit in filenames
- creating a dedicated admin full lane
- creating a dedicated user full lane
- preserving a tiny smoke subset that covers both admin and user
- updating project status documentation

This change does not include:

- changing application runtime behavior
- changing backend contracts
- introducing a reusable workflow or matrix refactor
- removing Docker-based E2E stack startup duplication between jobs

## Test Classification Model

The split is based on test ownership, not only URL base.

### Smoke

`E2E Smoke` remains the small cross-surface fail-fast gate. It keeps a very small subset of both admin and user flows.

The intent is:

- catch obvious breakage quickly
- avoid running broader suites when the stack is already broken
- preserve the existing smoke-first workflow the repository already uses

### Admin Full

`E2E Admin` covers operator/admin workflows end to end. It should include the broader admin regression suite, not just smoke labels.

Target admin coverage:

- admin auth guard/session flow
- compiled review happy path
- JSONL review happy path
- compiled review bulk job flow
- lexicon ops -> final DB import -> DB inspector flow
- voice import dry-run/import flow

### User Full

`E2E User` covers learner/user workflows end to end.

Target user coverage:

- auth/session learner behavior
- register/review empty path
- review submit
- review prompt-family flow
- knowledge map
- import-domain/import-create
- dashboard search
- import terminal completion flow

## File Naming Convention

Spec ownership should be visible directly in filenames.

### Smoke naming

- admin smoke files remain `admin-*.smoke.spec.ts`
- user smoke files become `user-*.smoke.spec.ts`

### Full naming

- admin full files become `admin-*.full.spec.ts` under `e2e/tests/full`
- user full files become `user-*.full.spec.ts` under `e2e/tests/full`

This convention makes CI routing straightforward and reduces the risk that a spec silently lands in the wrong job.

## CI Design

## `E2E Smoke`

Keep the current job structure largely intact:

- checkout
- install E2E dependencies
- start Docker stack
- wait for backend + learner frontend + admin frontend
- apply migrations
- run smoke suite
- upload artifacts
- tear down

This remains required.

## `E2E Admin`

Replace the current admin portion of `E2E Full` with a dedicated required job:

- `needs: [e2e-smoke]`
- same stack bootstrap pattern as current full job
- run admin full suite only
- upload artifacts separately
- tear down stack

This remains required.

## `E2E User`

Replace the user portion of `E2E Full` with a dedicated required job:

- `needs: [e2e-smoke]`
- same stack bootstrap pattern as current full job
- run user full suite only
- upload artifacts separately
- tear down stack

This remains required.

## Playwright Command Design

Keep Playwright config broadly unchanged for this slice.

The split should happen through npm scripts in `e2e/package.json`, using explicit file globs rather than tags.

Proposed commands:

- `test:smoke`
- `test:smoke:ci`
- `test:admin`
- `test:user`

Command intent:

- `test:admin` runs `e2e/tests/full/admin-*.spec.ts`
- `test:user` runs `e2e/tests/full/user-*.spec.ts`

Smoke continues using the existing `@smoke` marker strategy unless a later cleanup wants to make smoke path-based too.

## Admin Full Suite Construction

The repository does not currently have a true admin full lane. This change must create one.

The first admin full lane should be built from the existing durable admin scenarios rather than inventing new product coverage:

- promote or duplicate the current compiled review flow into full coverage
- promote or duplicate the current JSONL review flow into full coverage
- promote or duplicate the current final DB import + DB inspector flow into full coverage
- promote or duplicate the current voice import flow into full coverage
- promote or duplicate the current compiled review bulk job flow into full coverage

The smoke suite should remain a much smaller subset, so the admin full suite must not simply be the same files with new names.

## User Full Suite Construction

The current user full lane is already mostly represented by the existing full specs plus user-facing smoke flows. This change should make the split explicit and expand user full coverage only where needed to keep parity with the new admin full lane.

At minimum:

- rename current full specs to `user-*`
- keep them in `e2e/tests/full`
- ensure `E2E User` only targets user-owned full specs

## Risk Analysis

### Risk: Misclassified tests disappear from CI

If the split is done carelessly, a spec can fall out of all CI jobs.

Mitigation:

- make file ownership explicit in filenames
- use explicit file globs in npm scripts
- verify the selected file sets during implementation

### Risk: Admin full becomes just duplicated smoke

If the same minimal admin flows are used for both smoke and full, CI complexity goes up without improving coverage.

Mitigation:

- keep smoke intentionally tiny
- promote the broader existing admin scenarios into full

### Risk: CI wall-clock remains high

Because both admin and user full depend on smoke and still bootstrap separate Docker stacks, total duration will still include duplicated setup.

Mitigation:

- accept this for the current slice because the goal is structural clarity and isolation
- leave stack reuse/matrix optimization for a later CI-specific follow-up

## Verification Strategy

Implementation should verify:

- renamed test files are picked up correctly
- `npm run test:admin` resolves only admin full specs
- `npm run test:user` resolves only user full specs
- smoke still resolves the intended subset
- CI workflow syntax remains valid

Repository verification should include:

- targeted local Playwright command checks for file selection
- workflow lint/validation as applicable
- documentation/status updates

## Success Criteria

This design is complete when:

- `.github/workflows/ci.yml` no longer defines the old monolithic `E2E Full` gate
- CI defines required jobs:
  - `E2E Smoke`
  - `E2E Admin`
  - `E2E User`
- `E2E Admin` and `E2E User` both depend on `E2E Smoke`
- admin smoke and admin full are distinct
- user smoke and user full are distinct
- learner-side specs use `user-*` naming
- admin-side specs use `admin-*` naming
- `docs/status/project-status.md` records the new gate structure with verification evidence
