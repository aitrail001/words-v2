# Route Runtime Gate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch Next.js route/runtime regressions in `gate-fast`, `gate-full`, and CI by carrying forward the current admin bucket fix, adding structural guard tests, and introducing curated route/runtime sweep coverage.

**Architecture:** Start from a fresh isolated worktree branched from updated `main`, reapply the current local admin bucket fix there, then add a defense-in-depth test model: focused Jest serialization guards plus dedicated Playwright route/runtime sweeps wired through shared CI manifests and runners. Keep GitHub workflow logic thin by updating repo-owned scripts first and using CI YAML only for required suite wiring.

**Tech Stack:** Next.js 16 App Router with Turbopack dev, React 19, Jest, Playwright, shell-based CI runners under `scripts/ci`, GitHub Actions, Make-based gate commands, graphify.

---

### Task 1: Create The Isolated Worktree And Carry The Current Local Fix Forward

**Files:**
- Create: `.worktrees/route-runtime-gate-hardening/`
- Modify: `frontend/src/app/admin/review-queue/[bucket]/page.tsx`
- Modify: `frontend/src/components/review-queue/review-queue-shared.tsx`
- Modify: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`
- Modify: `graphify-out/GRAPH_REPORT.md`
- Modify: `graphify-out/graph.json`

- [ ] **Step 1: Refresh `main` and create the worktree**

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git worktree add .worktrees/route-runtime-gate-hardening -b feat/route-runtime-gate-hardening main
```

Expected: the worktree exists at `.worktrees/route-runtime-gate-hardening` on branch `feat/route-runtime-gate-hardening`.

- [ ] **Step 2: Bootstrap the new worktree**

Run: `make worktree-bootstrap`
Expected: the shared Python env links are created and local `node_modules` are installed in the worktree.

- [ ] **Step 3: Write the failing regression test for the admin bucket server/client boundary**

Test file: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`

Add a test that:

```ts
const tree = await AdminReviewQueueBucketPage({
  params: Promise.resolve({ bucket: "7d" }),
  searchParams: Promise.resolve({}),
});

const cardElement = findElementByType(tree, ReviewQueueItemCard);
expect(cardElement?.props.renderSupplementalFields).toBeUndefined();
expect(cardElement?.props.supplementalFields).toEqual([
  { label: "target_type", value: "meaning" },
  { label: "target_id", value: "meaning-1" },
  { label: "recheck_due_at", value: null },
  { label: "next_due_at", value: "2026-10-05T09:00:00+00:00" },
  { label: "last_outcome", value: "correct_tested" },
  { label: "relearning", value: false },
  { label: "relearning_trigger", value: null },
]);
```

Expected: this test fails before the implementation changes because the page currently passes a function prop.

- [ ] **Step 4: Run the focused Jest file to verify the RED state**

Run: `cd frontend && npx jest --runInBand --runTestsByPath 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx'`
Expected: FAIL with a mismatch showing the server page still passes `renderSupplementalFields`.

- [ ] **Step 5: Implement the minimal carry-forward fix**

Apply these code changes:

```ts
type ReviewQueueSupplementalField = {
  label: string;
  value: boolean | string | null | undefined;
};
```

```ts
export function ReviewQueueItemCard({
  item,
  bucket,
  allowStartReview = true,
  showStageLabel = false,
  supplementalFields,
}: {
  item: ReviewQueueItem | AdminReviewQueueItem;
  bucket?: ReviewQueueBucket;
  allowStartReview?: boolean;
  showStageLabel?: boolean;
  supplementalFields?: ReviewQueueSupplementalField[];
}) {
  ...
  {supplementalFields && supplementalFields.length > 0 ? (
    <div className="mt-3 space-y-1">
      {supplementalFields.map((field) => (
        <ReviewQueueDebugField key={field.label} label={field.label} value={field.value} />
      ))}
    </div>
  ) : null}
}
```

```ts
function buildAdminSupplementalFields(item: AdminReviewQueueItem) {
  return [
    { label: "target_type", value: item.target_type },
    { label: "target_id", value: item.target_id },
    { label: "recheck_due_at", value: item.recheck_due_at },
    { label: "next_due_at", value: item.next_due_at },
    { label: "last_outcome", value: item.last_outcome },
    { label: "relearning", value: item.relearning },
    { label: "relearning_trigger", value: item.relearning_trigger },
  ];
}
```

```tsx
<ReviewQueueItemCard
  key={item.queue_item_id}
  item={item}
  bucket={bucket}
  allowStartReview={false}
  supplementalFields={buildAdminSupplementalFields(item)}
/>
```

Expected: the page no longer passes a function prop into the client component.

- [ ] **Step 6: Verify the focused fix**

Run:

```bash
cd frontend && npx jest --runInBand --runTestsByPath 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx'
cd frontend && npm run lint
```

Expected: both commands pass.

- [ ] **Step 7: Rebuild the graph after the code changes**

Run: `uv run --with graphifyy python3.13 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`
Expected: `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md` update.

- [ ] **Step 8: Commit the carried-forward fix**

```bash
git add frontend/src/app/admin/review-queue/[bucket]/page.tsx frontend/src/components/review-queue/review-queue-shared.tsx frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx graphify-out
git commit -m "fix: serialize admin review queue debug fields"
```

Expected: the new branch now contains the local fix as a clean commit.

### Task 2: Formalize Route Runtime Coverage Targets And Shared Suite Membership

**Files:**
- Modify: `scripts/ci/test-groups.sh`
- Modify: `scripts/ci/run-e2e-suite.sh`
- Create: `e2e/tests/helpers/route-runtime-manifest.ts`
- Create: `e2e/tests/helpers/route-runtime-assertions.ts`

- [ ] **Step 1: Write the route manifest definitions before new tests**

Create `e2e/tests/helpers/route-runtime-manifest.ts` with typed manifests such as:

```ts
export type RouteRuntimeTarget = {
  name: string;
  path: string;
  requiresAdmin?: boolean;
  requiresLearner?: boolean;
  markerRole?: "heading" | "link" | "button" | "textbox";
  markerName: RegExp;
};

export const SMOKE_ROUTE_RUNTIME_TARGETS: RouteRuntimeTarget[] = [
  { name: "admin-queue-summary", path: "/admin/review-queue", requiresAdmin: true, markerRole: "heading", markerName: /admin review queue/i },
  { name: "admin-queue-bucket", path: "/admin/review-queue/1d", requiresAdmin: true, markerRole: "heading", markerName: /^1d$/i },
  { name: "learner-queue-summary", path: "/review/queue", requiresLearner: true, markerRole: "heading", markerName: /review queue/i },
  { name: "learner-queue-bucket", path: "/review/queue/1d", requiresLearner: true, markerRole: "heading", markerName: /^1d$/i },
];
```

Expected: the target list is explicit, typed, and fixture-aware.

- [ ] **Step 2: Add reusable runtime assertions**

Create `e2e/tests/helpers/route-runtime-assertions.ts` with helpers like:

```ts
export async function expectNoNextRuntimeFailure(page: Page) {
  await expect(page.locator("text=Application error")).toHaveCount(0);
  await expect(page.locator("text=Runtime Error")).toHaveCount(0);
  await expect(page.locator("nextjs-portal")).toHaveCount(0);
}
```

Expected: the suite has one shared place for runtime-failure checks instead of duplicating selectors.

- [ ] **Step 3: Extend the shared CI suite manifest**

Update `scripts/ci/test-groups.sh` to add new suite names:

```bash
declare -p E2E_SMOKE_SUITES >/dev/null 2>&1 || readonly -a E2E_SMOKE_SUITES=(smoke route-runtime-smoke)
declare -p E2E_REQUIRED_FULL_SUITES >/dev/null 2>&1 || readonly -a E2E_REQUIRED_FULL_SUITES=(review-srs admin user route-runtime-full)
```

Expected: gate membership begins in the shared manifest, not ad hoc elsewhere.

- [ ] **Step 4: Wire the new suite names into the repo-owned E2E runner**

Update `scripts/ci/run-e2e-suite.sh` so the new suite names dispatch to explicit npm/Playwright commands rather than inline shell fragments.
Expected: `run-e2e-suite.sh route-runtime-smoke` and `run-e2e-suite.sh route-runtime-full` become valid entry points.

- [ ] **Step 5: Commit the manifest and runner wiring**

```bash
git add scripts/ci/test-groups.sh scripts/ci/run-e2e-suite.sh e2e/tests/helpers/route-runtime-manifest.ts e2e/tests/helpers/route-runtime-assertions.ts
git commit -m "test: define route runtime suite manifests"
```

Expected: the suite topology is committed independently of the spec implementations.

### Task 3: Add The Smoke Route Runtime Sweep

**Files:**
- Create: `e2e/tests/smoke/route-runtime-smoke.spec.ts`
- Modify: `e2e/package.json`
- Modify: `scripts/ci/gate-fast.sh`

- [ ] **Step 1: Write the failing smoke sweep spec**

Create `e2e/tests/smoke/route-runtime-smoke.spec.ts` that iterates the smoke targets:

```ts
for (const target of SMOKE_ROUTE_RUNTIME_TARGETS) {
  test(`${target.name} renders without runtime errors`, async ({ page, adminPage, learnerPage }) => {
    const activePage = target.requiresAdmin ? adminPage : learnerPage ?? page;
    await activePage.goto(target.path);
    await expectNoNextRuntimeFailure(activePage);
    await expect(activePage.getByRole(target.markerRole ?? "heading", { name: target.markerName })).toBeVisible();
  });
}
```

Expected: the spec is present and initially red until the runner/package wiring exists.

- [ ] **Step 2: Add a direct package script for the smoke route sweep**

Update `e2e/package.json` with a script such as:

```json
"test:route-runtime:smoke": "playwright test tests/smoke/route-runtime-smoke.spec.ts --max-failures=1"
```

Expected: the new suite can run directly and through repo-owned scripts.

- [ ] **Step 3: Run the new smoke suite to verify the RED state**

Run: `./scripts/ci/run-e2e-suite.sh route-runtime-smoke`
Expected: FAIL initially if the runner wiring is incomplete or if route setup/auth assumptions are still wrong.

- [ ] **Step 4: Fix the suite setup until the smoke route sweep is green**

Use the smallest needed changes in the spec or helpers:

- reuse existing authenticated page fixtures instead of bespoke login logic
- use stable role/name markers only
- add fixture setup for parameterized routes only when the page genuinely requires it

Expected: the smoke route sweep becomes stable and deterministic.

- [ ] **Step 5: Add the suite to `gate-fast`**

Update `scripts/ci/gate-fast.sh` only through the existing suite loop fed by `E2E_SMOKE_SUITES`; do not add one-off custom shell logic.
Expected: `gate-fast` now runs the smoke route sweep automatically.

- [ ] **Step 6: Commit the smoke sweep**

```bash
git add e2e/tests/smoke/route-runtime-smoke.spec.ts e2e/package.json scripts/ci/gate-fast.sh
git commit -m "test: add smoke route runtime sweep"
```

Expected: the smoke route sweep lands as a self-contained change.

### Task 4: Add The Broader Full Route Runtime Sweep

**Files:**
- Modify: `e2e/tests/helpers/route-runtime-manifest.ts`
- Create: `e2e/tests/full/route-runtime.full.spec.ts`
- Modify: `e2e/package.json`
- Modify: `scripts/ci/gate-full.sh`

- [ ] **Step 1: Extend the route manifest for full coverage**

Add `FULL_ROUTE_RUNTIME_TARGETS` to `e2e/tests/helpers/route-runtime-manifest.ts` with a broader set such as:

```ts
export const FULL_ROUTE_RUNTIME_TARGETS: RouteRuntimeTarget[] = [
  ...SMOKE_ROUTE_RUNTIME_TARGETS,
  { name: "admin-queue-bucket-7d", path: "/admin/review-queue/7d", requiresAdmin: true, markerRole: "heading", markerName: /^7d$/i },
  { name: "learner-queue-bucket-7d", path: "/review/queue/7d", requiresLearner: true, markerRole: "heading", markerName: /^7d$/i },
  { name: "knowledge-map", path: "/knowledge-map", requiresLearner: true, markerRole: "heading", markerName: /knowledge map/i },
];
```

Expected: full coverage expands route breadth without duplicating smoke definitions manually.

- [ ] **Step 2: Write the full runtime sweep spec**

Create `e2e/tests/full/route-runtime.full.spec.ts` reusing the same assertions/helpers and iterating `FULL_ROUTE_RUNTIME_TARGETS`.
Expected: the full suite is structurally parallel to the smoke suite, not a second custom framework.

- [ ] **Step 3: Add a direct package script for the full route sweep**

Update `e2e/package.json` with:

```json
"test:route-runtime:full": "playwright test tests/full/route-runtime.full.spec.ts --max-failures=1"
```

Expected: the full suite is invocable directly and through `run-e2e-suite.sh`.

- [ ] **Step 4: Run the new full suite and fix any surfaced route/runtime regressions**

Run: `./scripts/ci/run-e2e-suite.sh route-runtime-full`
Expected: FAIL if uncovered runtime issues remain; fix each failing route at the smallest responsible boundary before rerunning.

- [ ] **Step 5: Keep the full-gate wiring shared**

Ensure `scripts/ci/gate-full.sh` relies on the updated `E2E_REQUIRED_FULL_SUITES` loop and does not special-case the new suite.
Expected: `gate-full` automatically includes the route runtime full sweep through shared manifest membership.

- [ ] **Step 6: Commit the full sweep**

```bash
git add e2e/tests/helpers/route-runtime-manifest.ts e2e/tests/full/route-runtime.full.spec.ts e2e/package.json scripts/ci/gate-full.sh
git commit -m "test: add full route runtime sweep"
```

Expected: the broader runtime sweep lands as a self-contained commit.

### Task 5: Harden Structural Jest Coverage Beyond The Current Reported Issue

**Files:**
- Modify: `frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx`
- Modify: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`
- Modify: any shared page-test helper extracted from those files

- [ ] **Step 1: Add a learner bucket structural guard mirroring the admin bucket guard**

Write a failing test in `frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx` that asserts the learner bucket page does not pass function props or other non-serializable props into its shared client card boundary.
Expected: if the learner path is already safe, the test should still encode the invariant explicitly.

- [ ] **Step 2: Extract a reusable helper for locating client elements in server page trees if duplication appears**

If both page test files need the same tree-walking helper, extract it into a local test utility under the same area.
Expected: the helper is only extracted if duplication is real.

- [ ] **Step 3: Run the focused frontend review-queue test files**

Run:

```bash
cd frontend && npx jest --runInBand --runTestsByPath 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx' 'src/app/review/queue/[bucket]/__tests__/page.test.tsx'
```

Expected: both files pass and establish the shared serialization invariant.

- [ ] **Step 4: Commit the structural guard expansion**

```bash
git add frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx
git commit -m "test: guard review queue server client boundaries"
```

Expected: the structural guard layer is now broader than the single reported bug.

### Task 6: Wire CI And Run The Real Gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `graphify-out/GRAPH_REPORT.md`
- Modify: `graphify-out/graph.json`

- [ ] **Step 1: Update GitHub workflow wiring only if suite/job boundaries require it**

Modify `.github/workflows/ci.yml` so the new suite names map to jobs only through repo-owned script entrypoints already added above.
Expected: no route-specific inline workflow logic is introduced.

- [ ] **Step 2: Rebuild the graph after final code changes**

Run: `uv run --with graphifyy python3.13 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`
Expected: `graphify-out` reflects the final code state.

- [ ] **Step 3: Run the smallest direct validations for the changed slices**

Run:

```bash
cd frontend && npm run lint
cd frontend && npx jest --runInBand --runTestsByPath 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx' 'src/app/review/queue/[bucket]/__tests__/page.test.tsx'
./scripts/ci/run-e2e-suite.sh route-runtime-smoke
./scripts/ci/run-e2e-suite.sh route-runtime-full
```

Expected: all changed-slice validations pass before the full gates.

- [ ] **Step 4: Run the canonical repo gates**

Run:

```bash
make gate-fast
make gate-full
```

Expected: both gates pass on the implementation branch. If either gate exposes additional runtime regressions, fix them before proceeding and rerun the gate from the top.

- [ ] **Step 5: Commit the final gate/CI updates**

```bash
git add .github/workflows/ci.yml graphify-out
git commit -m "ci: add route runtime gate coverage"
```

Expected: the branch ends with passing local gates and committed CI wiring.
