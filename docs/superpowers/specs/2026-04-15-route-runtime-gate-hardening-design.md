# Route Runtime Gate Hardening Design

## Goal

Harden `gate-fast`, `gate-full`, and GitHub CI so they catch Next.js route/runtime failures that lint, unit tests, and production builds can miss, especially Server Component to Client Component boundary errors on real rendered routes.

## Problem Statement

The recent `/admin/review-queue/[bucket]` regression was a real runtime failure in local development:

- a server page passed a function prop into a client component
- Jest page tests still passed because they rendered the server component output directly
- `next build` still passed
- existing E2E coverage exercised adjacent flows and APIs, but did not visit the exact rendered bucket route

This exposed a gap in the current test loops:

- `gate-fast` has strong subset and smoke coverage, but not a broad enough route/runtime sweep for Next 16 server/client serialization errors
- `gate-full` has strong full-flow coverage, but still relies on scenario-driven suites rather than a deliberate route census
- CI correctly mirrors repo-owned scripts, but currently inherits the same route/runtime blind spots

## Constraints

- Keep GitHub workflows thin wrappers over repo-owned scripts and manifests
- Start all CI-relevant suite membership changes in `scripts/ci/test-groups.sh`
- Do not add an uncontrolled crawler over every route
- Preserve fail-fast ordering and keep `gate-fast` useful for inner-loop verification
- Favor stable, high-signal assertions over brittle UI-detail assertions

## Existing Coverage

### Strong areas

- Backend subset and full suites
- Frontend/admin lint and Jest coverage
- Existing E2E smoke workflows
- Existing required full E2E suites for review/SRS, admin, and user workflows
- Admin queue summary and API-level `effective_now` coverage

### Current gap

Route rendering coverage is incomplete for parameterized pages and server-heavy pages that compose client children. This is where Next 16 runtime boundary regressions are most likely to surface.

## Options Considered

### 1. Expand existing scenario E2E suites only

Add more assertions into current smoke/full scenarios and rely on those to catch route/runtime regressions.

Pros:

- minimal new suite surface
- reuses existing fixtures directly

Cons:

- route coverage remains incidental rather than deliberate
- blind spots persist when a page is not already the focus of a scenario

### 2. Dedicated route/runtime sweep only

Add a new Playwright suite that visits a curated manifest of routes in a running app and asserts they render without runtime failures.

Pros:

- directly targets the missing bug class
- easier to reason about route coverage

Cons:

- structural bugs may still be caught later than necessary
- route manifest alone does not explain root cause when it fails

### 3. Hybrid defense-in-depth (recommended)

Combine:

- focused structural guard tests for risky server/client boundaries
- a curated route/runtime sweep in Playwright smoke
- a broader companion sweep in full E2E

Pros:

- catches the bug class at both structure and runtime layers
- gives fast, precise failures in unit tests and realistic failures in running app tests
- scales to broader route coverage without relying on a brittle crawler

Cons:

- more maintenance than a single-layer solution
- slightly slower gate times

## Recommended Design

Use the hybrid approach.

### Layer 1: Structural boundary guards

Add or extend focused Jest tests for known risky patterns:

- server pages rendering shared client components
- props crossing the server/client boundary
- parameterized server routes composing shared UI primitives

These tests should assert that server pages pass only serialized data into client components. They are not a replacement for runtime coverage, but they give fast feedback and narrow failures.

### Layer 2: Route/runtime sweep in smoke

Add a dedicated E2E suite for high-signal route rendering checks. This suite should:

- boot the real stack
- authenticate where needed
- visit a curated manifest of learner and admin routes
- assert absence of runtime error shells or Next error overlays
- assert presence of a stable page marker per route

This suite should be part of `gate-fast` and the CI smoke layer.

### Layer 3: Broader route/runtime sweep in full

Add a broader companion sweep for `gate-full` and required CI full coverage. This should extend coverage to:

- parameterized queue routes
- detail pages linked from queue/list surfaces
- admin-only routes that depend on seeded state
- server-heavy pages that fetch on the server and render client children

The full sweep should reuse the same helper model and route manifest pattern as the smoke sweep, not a separate implementation.

## Route Selection Strategy

Do not attempt to crawl everything.

Maintain curated manifests with stable, fixture-aware targets.

### Smoke manifest

Include high-signal critical routes such as:

- learner review queue summary
- learner review queue bucket
- admin review queue summary
- admin review queue bucket
- one or two server-heavy detail pages already supported by fixtures

### Full manifest

Extend coverage with:

- additional learner/admin parameterized routes
- detail pages reached from existing scenarios
- pages with known server-side fetch plus client-child composition

Each route entry should define:

- route path
- required auth/user role
- required fixture/setup
- stable assertion target

## Gate Wiring Changes

### `gate-fast`

Add the new runtime sweep as an explicit E2E suite in the smoke tier. It should run through existing repo-owned E2E runners and be listed in `scripts/ci/test-groups.sh`.

### `gate-full`

Add the broader runtime sweep through the same suite wiring model used by other required full E2E suites.

### CI

Update `.github/workflows/ci.yml` only as needed to reflect new suite boundaries from shared scripts and manifests. No inline workflow-specific route logic.

## Test Ownership and Files

Expected areas to change:

- `scripts/ci/test-groups.sh`
- `scripts/ci/gate-fast.sh`
- `scripts/ci/gate-full.sh`
- `scripts/ci/run-e2e-suite.sh` and any E2E helper wiring needed for the new suite names
- `.github/workflows/ci.yml` only if required suite/job wiring changes
- `e2e/tests/smoke/*` or a dedicated route-runtime smoke spec
- `e2e/tests/full/*` or a dedicated route-runtime full spec
- frontend/admin Jest tests for structural serialization guards

## Success Criteria

The work is successful when:

- the current `/admin/review-queue/[bucket]` regression is covered by automated tests
- `gate-fast` catches high-signal route/runtime regressions in a running app
- `gate-full` broadens route/runtime coverage beyond scenario-only workflows
- CI remains aligned with local gates through shared scripts/manifests
- added coverage is curated and stable, not a flaky crawler

## Risks

### Slower `gate-fast`

Broader runtime coverage will increase `gate-fast` time. Keep the smoke manifest tightly curated.

### Fixture brittleness

Parameterized routes can be fragile if they depend on inconsistent test state. Reuse existing seeded scenarios and helper patterns wherever possible.

### Duplicate coverage

Some routes are already visited indirectly by workflow scenarios. The new suite should prioritize render-risk coverage, not duplicate end-to-end business assertions unnecessarily.

## Out of Scope

- generic full-site crawling
- visual regression testing
- broad unrelated refactors to route architecture
- replacing existing workflow E2E suites with route sweeps

## Implementation Direction

Implement on a new isolated worktree/branch, carry forward the current local fix for the admin bucket page, then:

1. formalize route/runtime coverage gaps
2. add structural guard tests
3. add smoke route/runtime sweep coverage
4. add broader full route/runtime sweep coverage
5. wire suites into `gate-fast`, `gate-full`, and CI through shared manifests
6. run the affected gates and fix any regressions exposed by the new coverage
