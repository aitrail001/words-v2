# Knowledge Map Overview/Range Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the current knowledge-map page so `/knowledge-map` is overview-only and `/knowledge-map/range/[start]` owns all per-range detail interactions.

**Architecture:** Keep existing backend APIs. Extract the current range-detail behavior into a shared client component, simplify the overview route to the full-board map, and add a dedicated dynamic route for each 100-entry range.

**Tech Stack:** Next.js App Router, React client components, Jest + Testing Library, existing learner knowledge-map client.

---

### Task 1: Add failing tests for the new route split

**Files:**
- Modify: `frontend/src/app/knowledge-map/__tests__/page.test.tsx`
- Create: `frontend/src/app/knowledge-map/range/[start]/__tests__/page.test.tsx`

**Step 1: Write the failing overview test**

Update the current `/knowledge-map` test to assert:

- the overview tile grid still renders
- the overview page does **not** render `knowledge-card-view`
- the overview page does **not** render `knowledge-range-strip`
- the overview range tile links to `/knowledge-map/range/1`

**Step 2: Write the failing range-route tests**

Add tests for `/knowledge-map/range/[start]` that assert:

- the selected range detail loads from route param `1`
- cards/tags/list views render there
- previous/next range controls navigate to `/knowledge-map/range/[other-start]`
- entry/definition sync regression still holds on this route

**Step 3: Run tests to verify failure**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand --runTestsByPath 'frontend/src/app/knowledge-map/__tests__/page.test.tsx' 'frontend/src/app/knowledge-map/range/[start]/__tests__/page.test.tsx'
```

Expected:

- overview assertions fail because `/knowledge-map` still renders the range detail
- new range-route test fails because the route/page does not exist yet

### Task 2: Extract the shared range-detail component

**Files:**
- Create: `frontend/src/components/knowledge-map-range-detail.tsx`
- Modify: `frontend/src/app/knowledge-map/page.tsx`

**Step 1: Move current detail behavior into the new component**

Extract into `knowledge-map-range-detail.tsx`:

- user preference loading
- range loading by `rangeStart`
- selected entry state
- entry-detail cache
- meaning navigation
- cards/tags/list rendering
- entry-status updates
- mini range strip

**Step 2: Parameterize route navigation**

The component should accept `initialRangeStart: number` and use the API `previous_range_start` / `next_range_start` to render left/right range navigation links to `/knowledge-map/range/[start]`.

**Step 3: Keep the fetch-loop fix intact**

Ensure the component preserves:

- stable `entry_type:entry_id` detail caching
- entry/definition sync guard
- no repeated refetch when revisiting a previously viewed entry

### Task 3: Simplify the overview page

**Files:**
- Modify: `frontend/src/app/knowledge-map/page.tsx`

**Step 1: Strip the page down to overview-only behavior**

Keep only:

- overview fetch
- title and explanatory copy
- dense range grid

Remove:

- selected-range state
- entry-detail state
- cards/tags/list controls
- mini strip
- range detail card/list/tags surfaces

**Step 2: Make tiles link to the range route**

Each tile should navigate to:

```text
/knowledge-map/range/[range_start]
```

### Task 4: Add the new range route

**Files:**
- Create: `frontend/src/app/knowledge-map/range/[start]/page.tsx`

**Step 1: Implement the route wrapper**

Read the `start` param, validate it, and render the shared `KnowledgeMapRangeDetail` component.

**Step 2: Handle invalid params safely**

If the route param is not a positive integer, render a safe fallback or `notFound()`.

### Task 5: Run focused verification

**Files:**
- Modify if needed: `frontend/src/app/knowledge-map/__tests__/page.test.tsx`
- Modify if needed: `frontend/src/app/knowledge-map/range/[start]/__tests__/page.test.tsx`

**Step 1: Run focused Jest**

Run:

```bash
NODE_PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules PATH=/Users/johnson/AI/src/words-v2/frontend/node_modules/.bin:$PATH jest --config frontend/jest.config.js --runInBand --runTestsByPath 'frontend/src/app/knowledge-map/__tests__/page.test.tsx' 'frontend/src/app/knowledge-map/range/[start]/__tests__/page.test.tsx'
```

Expected:

- all tests pass

**Step 2: Run diff hygiene**

Run:

```bash
git diff --check
```

Expected:

- pass

### Task 6: Live Docker verification

**Files:**
- Modify only if a bug is found during live verification

**Step 1: Use the current bugfix worktree stack**

Bring up the current worktree stack, migrate, and import the full fixture if needed.

**Step 2: Verify overview/detail split**

Confirm manually or with a one-off browser script:

- `/knowledge-map` shows only the global map board
- clicking a range tile lands on `/knowledge-map/range/[start]`
- the range page shows cards/tags/list detail
- bottom previous/next arrows move between adjacent range routes
- bottom mini strip still changes entries within the current range

**Step 3: Reconfirm no card-detail desync**

Verify that moving between entries inside the range page keeps the visible definition aligned with the selected entry and does not trigger repeated entry-detail request loops.

### Task 7: Update status docs

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Add a status change log entry**

Record:

- route split from overview to dedicated range detail
- verification commands/results
- any known remaining limitations
