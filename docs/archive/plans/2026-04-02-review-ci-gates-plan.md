# Review CI Gates Plan

**Status:** COMPLETED

**Scope:** Make learner review/SRS coverage explicit in GitHub CI so backend regressions, frontend regressions, and Playwright review smoke are visible as dedicated gates instead of only being implied by broad suite jobs.

## Goals

1. Add an explicit backend review/SRS regression step to CI.
2. Add an explicit frontend review/SRS regression step to CI.
3. Add a dedicated review-focused Playwright smoke gate in CI.
4. Keep the existing broad backend/frontend/smoke jobs intact so overall coverage does not shrink.
5. Update the project status board with the new gate definition and verification evidence.

## Planned Changes

1. Add focused test scripts for the learner review path where it improves maintainability.
2. Update `.github/workflows/ci.yml` to:
   - run review/SRS backend tests as a named step before the broad backend suite
   - run review/SRS frontend tests as a named step before the broad frontend suite
   - run a dedicated learner-review Playwright smoke job before the broader smoke workflow
3. Verify the targeted backend/frontend commands locally.
4. Verify the new E2E script resolves the intended smoke files.
5. Update `docs/status/project-status.md` with the new CI gate and commands used.

## Verification Target

1. `pytest` focused on review/SRS backend files
2. `npm`/`jest` focused on review/SRS frontend files
3. Playwright review smoke test discovery via the new CI command
4. `git diff --check`

## Completion Notes

1. `frontend/package.json` now exposes `test:review` for the learner review/SRS Jest slice.
2. `e2e/package.json` now exposes `test:review:ci` for the learner review Playwright smoke slice.
3. `.github/workflows/ci.yml` now runs named review/SRS regression steps in the backend and frontend jobs and adds a dedicated `E2E Review + SRS Smoke (required)` gate before the broader smoke lane.
4. `docs/status/project-status.md` records the CI gate update and fresh verification evidence.
