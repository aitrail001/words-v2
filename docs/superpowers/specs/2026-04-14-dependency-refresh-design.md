# Dependency Refresh Design

## Goal

Upgrade the requested packages in `frontend`, `admin-frontend`, `e2e`, and `tools/lexicon/node`, regenerate the relevant lockfiles, review and fix any resulting code or config incompatibilities, and verify the repo is still in a review-ready state.

## Scope

This work covers these manifests:

- `frontend/package.json`
- `admin-frontend/package.json`
- `e2e/package.json`
- `tools/lexicon/node/package.json`

Requested version targets:

- `frontend/package.json` and `admin-frontend/package.json`
  - `next`: `^16.2.3`
  - `react`: `^19.2.5`
  - `react-dom`: `^19.2.5`
  - `jest`: `^30.3.0`
  - `jest-environment-jsdom`: `^30.3.0`
  - `eslint`: `^10.2.0`
  - `typescript`: `^6.0.2`
  - `@types/node`: `^25.6.0`
  - `ts-jest`: `^29.4.9`
  - `tailwindcss`: `^4.2.2`
  - `@tailwindcss/postcss`: `^4.2.2`
  - `zustand`: `^5.0.12`
  - `@types/react` and `@types/react-dom`: latest `^19.x`
- `e2e/package.json`
  - `typescript`: `^6.0.2`
  - `@types/node`: `^25.6.0`
  - `@types/pg`: `^8.20.0`
- `tools/lexicon/node/package.json`
  - `openai`: `^6.34.0`

## Non-Goals

- Normalizing the repo onto a single package manager.
- Unrelated refactors outside upgrade-driven remediation.
- Broad framework modernization beyond what is required to keep the upgraded packages working.
- Runtime-shape changes that conflict with the repo's local-dev and gate-stack guidance.

## Current Constraints

- The repo uses mixed workspace-level lockfile and package-manager state today.
- Recent `next16` upgrade work already exists in history, so compatibility review must distinguish between existing modernization and breakage caused by this refresh.
- Repo policy requires exact reporting of what verification ran.
- `make gate-fast`, `make gate-full`, and the repo CI scripts must be run outside the sandbox on the first attempt.
- After code changes, the graph must be rebuilt under `graphify-out/`.

## Tracked Working Context

These paths are part of the requested working context and must be reviewed for upgrade impact:

- `.codex/`
- `.env.stack.ci`
- `.env.stack.gate`
- `graphify-out/`
- `.githooks/`

The default expectation is that package-driven changes will mainly land in workspace manifests, lockfiles, app/test/config files, and `graphify-out/` after rebuild. Changes to the other tracked paths should happen only if verification demonstrates they are needed for compatibility with the upgraded toolchain.

## Execution Strategy

The work will use an aggressive coordinated refresh rather than a conservative workspace-by-workspace rollout.

Sequence:

1. Update all requested dependency versions across the four target manifests.
2. Regenerate workspace lockfiles using the package manager currently in use in each workspace rather than normalizing package managers as part of this task.
3. Run installs and collect the first wave of failures from tests, typechecks, lint, and builds.
4. Apply the smallest safe code or config fixes needed to restore compatibility with the upgraded packages.
5. Re-run targeted verification.
6. Run repo-level gate verification.
7. Rebuild the graph.

This approach intentionally optimizes for a single cross-repo remediation pass after installs. It accepts a wider first failure surface in exchange for fewer partial upgrade cycles.

## Package Manager And Lockfile Handling

Lockfiles will be regenerated in place for the workspaces that already maintain them.

Observed current state:

- `frontend/` contains `package-lock.json` and `pnpm-lock.yaml`
- `admin-frontend/` contains `package-lock.json`
- `e2e/` contains `package-lock.json` and `pnpm-lock.yaml`
- `tools/lexicon/node/` contains `package-lock.json`

Plan:

- Preserve the current workspace-local package-manager reality during this task.
- Refresh lockfiles rather than deleting them preemptively.
- Only remove a lockfile if the install workflow or repo conventions make it clearly redundant and keeping it would make installs misleading or non-deterministic.
- Record which install command was used in each workspace as part of verification reporting.

## Expected Compatibility Hotspots

### Frontend and admin frontend

Primary risk areas:

- Next.js and `eslint-config-next` compatibility with `eslint@10`
- Jest 30 compatibility with current Jest config, setup files, and `ts-jest`
- TypeScript 6 compatibility with application code, test code, and config files
- React 19 type updates
- `zustand@5` store typing or selector behavior
- Tailwind 4.2 and `@tailwindcss/postcss` integration with existing PostCSS/Tailwind config

Expected remediation types:

- Jest config or setup-file edits
- ESLint config updates
- Type fixes in app code or tests
- Small import or typing changes in Zustand stores
- PostCSS or Tailwind config alignment

### E2E

Primary risk areas:

- TypeScript 6 compatibility in Playwright config and helpers
- Node 25 type changes
- Updated `@types/pg` types in DB helper code

Expected remediation types:

- Type-only fixes in Playwright support files
- Small config or helper cleanup where stricter typing surfaces latent issues

### Lexicon Node transport

Primary risk areas:

- OpenAI client construction
- Request/response handling assumptions
- Environment or transport wrapper code

Expected remediation types:

- Minimal API-shape updates if the installed `openai` client version exposes changed types or stricter usage

## Testing And Verification

Verification will proceed from local workspace checks to repo gates.

### Workspace-level verification

Run the smallest relevant commands after installs and after remediation, such as:

- `frontend`: install, tests, lint, build
- `admin-frontend`: install, tests, lint, build
- `e2e`: install, typecheck, targeted Playwright validation if needed
- `tools/lexicon/node`: install plus any available smoke or compatibility check for the transport code

The exact commands will be chosen from the workspace scripts and repo conventions at execution time and reported verbatim.

### Repo-level verification

After targeted workspace checks are green:

- run `make gate-fast`
- run `make gate-full` if the refresh affects review-facing readiness or if the branch is being prepared for review

These commands must be run outside the sandbox on the first attempt.

### Verification reporting

The final implementation report must include:

- exact commands run
- pass/fail result for each
- what was intentionally not run
- any remaining residual risk

## TDD And Remediation Rules

Upgrade-driven production changes must follow TDD where behavior changes or regressions are being fixed:

- reproduce the failing behavior with a test when feasible
- watch the test fail for the intended reason
- implement the smallest fix
- rerun the relevant test target

Pure manifest and lockfile updates do not require TDD. Config-only compatibility edits should still be verified directly with the command that previously failed.

## Architecture And Change Boundaries

The implementation should prefer narrow fixes in the existing app structures.

Guidelines:

- Preserve current architectural patterns in `frontend/` and `admin-frontend/`
- Avoid opportunistic refactors
- Keep any remediation close to the failing boundary: config in config files, test harness issues in test setup, type issues in the smallest affected module
- Treat the tracked repo-level files as review context, not automatic edit targets

## Risks

- `eslint@10` may require config changes that are not yet reflected in `eslint-config-next`
- `jest@30` and `ts-jest@29.4.9` may expose a version-compatibility gap
- `typescript@6` may surface a larger-than-expected number of type errors in test code or framework config
- Mixed lockfile state may make install output ambiguous if not handled carefully

## Success Criteria

The task is complete when:

- all requested manifest versions are updated
- relevant lockfiles are regenerated
- upgrade-induced compatibility issues are fixed
- targeted workspace verification passes, or any remaining failures are explicitly documented with cause
- repo-level verification is run and reported
- `graphify-out/` is rebuilt after code changes

