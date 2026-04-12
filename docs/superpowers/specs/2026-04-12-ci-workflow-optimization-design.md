# CI Workflow Optimization Design

**Date:** 2026-04-12
**Branch:** `ci-workflow-optimization`

## Goal

Unify local gate execution and GitHub CI around repo-owned scripts in `scripts/ci/` so the same test selections, stack behavior, and suite boundaries are exercised locally before push/PR and in GitHub after push. The target state is that `make gate-fast` and `make gate-full` are the canonical local readiness commands, while `.github/workflows/ci.yml` remains the GitHub gate as a thin wrapper over the same script layer.

## Scope

This design covers:

- refactoring `.github/workflows/ci.yml` to delegate gate logic to `scripts/ci/*`
- finishing the new `scripts/ci/` runner layer so every required GitHub check has a script entry point
- centralizing CI-relevant test grouping in `scripts/ci/test-groups.sh`
- clarifying the role of `gate-*` versus `local-ci-*`
- normalizing structured gate artifacts and logs
- aligning `AGENTS.md` with the actual gate contract

This design does not change the required GitHub job topology beyond making it script-driven. It preserves separate required jobs for backend, frontend, admin frontend, lexicon, smoke E2E, and full E2E lanes.

## Desired End State

The repo should have one CI contract with different wrappers:

- `make gate-fast` and `make gate-full` are the canonical human-facing local readiness checks
- `local-ci-*` remains available only as CI-like stack and debugging utilities
- `.github/workflows/ci.yml` remains split into separate required jobs, but each job calls a repo-owned script instead of duplicating gate logic inline
- `scripts/ci/test-groups.sh` is the first place to update when CI-relevant tests are added, removed, renamed, or reclassified

## Decisions

### 1. Canonical env file

Use `.env.stack.gate` as the canonical disposable gate env file everywhere in the local gate flow and the repo policy documentation. Remove references to `.env.stack.pr` from gate policy text.

### 2. Canonical local gate entry points

Use:

- `make gate-fast`
- `make gate-full`

as the only documented branch-readiness and PR-readiness commands.

Inner-loop commands such as `make test-backend`, `make test-frontend`, `make test-admin`, and `make smoke-local` remain useful for development, but they are not the sign-off gate. `local-ci-*` is retained, but not as a competing gate.

### 3. Keep separate GitHub required jobs

GitHub should keep separate required jobs rather than collapsing into one aggregate gate job. Each required job remains visible in the PR UI and preserves fast failure isolation:

- backend
- frontend
- admin-frontend
- lexicon
- e2e-smoke
- e2e-review-srs
- e2e-admin
- e2e-user

The change is not the job graph. The change is moving job logic into `scripts/ci/*`.

### 4. Keep `local-ci-*`, but narrow its meaning

Keep `local-ci-*` because it still has operational value:

- bringing up a CI-like stack once for repeated debugging
- inspecting logs and container state
- rerunning suites against a persistent local CI-like stack
- investigating startup, migration, and E2E issues interactively

However, `local-ci-*` must no longer imply “this is the canonical gate.” The canonical gate remains `gate-fast` and `gate-full`.

The intended split is:

- `gate-*`: branch-readiness and PR-readiness verification
- `local-ci-*`: CI-like stack lifecycle and manual debugging utilities

### 5. Normalize gate artifacts and logs

Use `artifacts/ci-gate/<label>` as the normalized output root for structured logs and artifacts produced by `scripts/ci/*`.

Examples:

- `artifacts/ci-gate/backend-subset`
- `artifacts/ci-gate/backend-full`
- `artifacts/ci-gate/e2e-smoke`
- `artifacts/ci-gate/e2e-review-srs`
- `artifacts/ci-gate/lexicon-gate`

Interactive stack lifecycle commands such as `local-ci-up`, `local-ci-down`, `local-ci-logs`, and `local-ci-ps` do not need to create bundled artifact directories. Commands that execute a verification suite through `scripts/ci/*` should use the normalized output root.

## Script Architecture

### Shared files

#### `scripts/ci/test-groups.sh`

This is the canonical manifest for CI-relevant suite membership and test classification. It should own:

- backend fast subset file lists
- frontend/admin/lexicon suite mode naming when a shared manifest is useful
- E2E lane naming and any future grouped subsets

Rule: when adding, removing, renaming, or reclassifying tests that affect branch readiness or release confidence, update `scripts/ci/test-groups.sh` first.

The purpose of this rule is to minimize modifications elsewhere. Runner and gate scripts should consume shared definitions rather than re-declare membership.

#### `scripts/ci/lib.sh`

This file should own shared CI shell helpers only:

- env loading and validation
- compose wrappers
- readiness checks
- migration helpers
- log and artifact collection
- common path and label helpers

It should not become the place where all suite-specific behavior accumulates. Mode-specific test selection should stay in the runner scripts, using data from `test-groups.sh`.

### Runner scripts

The repo should have a dedicated runner script for every GitHub-required check whose logic would otherwise live in YAML:

- `scripts/ci/run-backend-suite.sh`
- `scripts/ci/run-frontend-suite.sh`
- `scripts/ci/run-admin-suite.sh`
- `scripts/ci/run-lexicon-suite.sh`
- `scripts/ci/run-e2e-suite.sh`

Responsibilities:

- choose the appropriate command for a named mode
- source `test-groups.sh` where shared suite definitions are needed
- use shared helpers from `lib.sh`
- write structured outputs to `artifacts/ci-gate/<label>` where applicable

### Gate scripts

The gate scripts orchestrate runner scripts:

- `scripts/ci/gate-fast.sh`
- `scripts/ci/gate-full.sh`

Responsibilities:

- define which runner modes make up the fast and full gates
- keep local readiness semantics aligned with GitHub required checks
- avoid hardcoding duplicate suite membership already present in `test-groups.sh`

## Required Refactor by Area

### Backend

`run-backend-suite.sh` already exists, but its subset mode still hardcodes the backend file list. It should source `FAST_BACKEND_SUBSET` from `test-groups.sh` so subset membership only lives in one place.

### Frontend

Introduce `run-frontend-suite.sh` with modes that represent the GitHub frontend check and the local gate variants. At minimum:

- `subset`: the review/SRS regression subset used by the fast gate
- `full`: full frontend test suite plus production build
- `lint`, `test`, and `build`: explicit component modes so both local gates and GitHub wrappers can compose the same frontend behavior without reintroducing inline command duplication

The subset command should be sourced from `test-groups.sh` rather than repeated in multiple locations.

### Admin frontend

Introduce `run-admin-suite.sh` so GitHub no longer owns the command sequence inline. At minimum:

- `subset` or `gate-fast`: lint plus current test command if that remains part of the fast gate
- `full`: full admin test suite plus production build

If admin has no meaningful “subset” beyond its current lint/test behavior, that should still be represented as a named script mode rather than embedded in YAML and gate scripts separately.

### Lexicon

Introduce `run-lexicon-suite.sh` because lexicon is already a first-class gate lane and still has bespoke job logic in YAML. Recommended modes:

- `full`: current CI lexicon test suite
- `smoke`: current lexicon smoke flow
- `gate`: run the full suite and then the smoke flow

This gives both local gates and GitHub a single repo-owned entry point for lexicon behavior.

### E2E

Keep `run-e2e-suite.sh`, but tighten its contract:

- continue to support named suites such as `smoke`, `review-srs`, `admin`, `user`, and `full`
- keep suite naming and grouping aligned with `test-groups.sh`
- keep stack startup, readiness checks, migrations, log collection, and teardown in the repo script layer rather than YAML

`local-ci-smoke` and `local-ci-full` should become wrappers over the same script layer so their outputs land under `artifacts/ci-gate/<label>` too.

## GitHub Workflow Shape

Treat `.github/workflows/ci.yml` as the GitHub gate. It should stay a thin wrapper around repo-owned CI scripts.

After the refactor, the YAML should still own:

- event triggers
- job graph and `needs`
- runtime setup and dependency caching
- invoking the appropriate repo-owned script
- uploading artifacts generated by the script layer

The YAML should stop owning duplicated versions of:

- docker stack boot sequences
- readiness polling loops
- migration execution logic
- suite membership and subset lists
- bespoke per-job log collection procedures already implemented in repo scripts

In practice, each job should converge toward:

1. checkout
2. setup runtime and caches
3. install dependencies required for that lane
4. run one repo-owned script with a named mode
5. upload artifacts from `artifacts/ci-gate/<label>` and test output directories

## Mapping of Gates to Lanes

The full gate should mirror the set of required GitHub checks.

Recommended composition:

### `gate-fast`

- backend fast subset
- frontend fast subset
- admin fast suite
- lexicon gate or an explicitly chosen lexicon fast equivalent if one exists
- e2e smoke

This is the fail-fast local verification entry point after non-trivial changes and before pushing branch updates that are not yet final PR sign-off.

### `gate-full`

- everything in `gate-fast`
- full backend suite
- full frontend suite and build
- full admin suite and build
- full lexicon gate
- `e2e-review-srs`
- `e2e-admin`
- `e2e-user`

This is the local pre-PR sign-off command and should remain aligned with the required GitHub gate.

If a lexicon fast/full distinction is not worth maintaining, the design prefers one lexicon gate mode used in both places instead of inventing a fake split.

## AGENTS.md Updates

Update `AGENTS.md` to match the real contract:

- standardize on `.env.stack.gate`
- keep `gate-fast` and `gate-full` as the canonical readiness commands
- explicitly describe `local-ci-*` as CI-like stack/debugging utilities
- reinforce that `scripts/ci/test-groups.sh` is the first place to update when CI-relevant tests move
- keep the GitHub gate thin-wrapper rule for `.github/workflows/ci.yml`
- keep the requirement that local and GitHub gates must not drift

## Error Handling and Verification Expectations

Every runner script should:

- fail clearly on unknown modes
- validate required env inputs
- collect structured logs on failure
- clean up disposable stacks where appropriate

Verification for the refactor should cover:

- shell linting or at least execution sanity for new scripts
- `make gate-fast`
- focused script-mode checks for any newly added runner scripts
- a CI workflow syntax/config validation pass

The exact implementation should favor the smallest safe proof that the scripts and wrappers are correctly wired, while still confirming that the required checks route through the repo-owned script layer.

## Risks and Mitigations

### Risk: duplicated logic remains in YAML

Mitigation: every required GitHub lane must have a corresponding script entry point, even if the script is thin.

### Risk: `test-groups.sh` becomes incomplete and drift returns

Mitigation: codify in `AGENTS.md` and script comments that CI-relevant test membership updates start there first.

### Risk: `local-ci-*` keeps confusing contributors

Mitigation: rename help text and docs to describe it as CI-like stack/debugging utilities, not readiness gates.

### Risk: artifact collection becomes inconsistent across commands

Mitigation: make `lib.sh` own the normalized `artifacts/ci-gate/<label>` path helper and keep suite-running commands on that path.

## Implementation Notes

The expected implementation is a refactor, not a redesign of the job graph. Preserve current required GitHub lane separation and current gate intent, but consolidate test selection and lane behavior into `scripts/ci/*` so local and GitHub verification share the same contract.
