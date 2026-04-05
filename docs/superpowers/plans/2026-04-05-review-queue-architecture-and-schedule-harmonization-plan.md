# Review Queue Architecture and Schedule Harmonization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat review queue pages with a shared summary/detail queue architecture, seed admin review data, unify learner-visible next-review truth around actual scheduled timestamps, and add full scenario coverage for queue/SRS behavior.

**Architecture:** Build shared backend queue summary/detail projections and shared frontend review-queue components, then compose learner and admin summary/detail routes from those shared units. Fix detail-page schedule payloads so queue and detail read from the same scheduled timestamp, while keeping manual next-review choices as explicit overrides rather than the displayed source of truth.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Next.js App Router, React, Jest, pytest, Playwright, local deterministic review seed scripts.

---

## File Structure

### Backend

- Modify: `backend/app/services/review.py`
  - Add shared queue summary/detail projection helpers, sorting support, and schedule-payload harmonization.
- Modify: `backend/app/api/reviews.py`
  - Add learner/admin bucket detail endpoints and summary/detail response models.
- Modify: `backend/app/spaced_repetition.py`
  - Keep prompt-family weighting explicit and add long-horizon test seams if needed.
- Test: `backend/tests/test_review_service.py`
  - Add unit coverage for summary/detail grouping, sorting, exact schedule payloads, and long-horizon progression.
- Test: `backend/tests/test_review_api.py`
  - Add API coverage for learner/admin summary and bucket detail routes plus effective-time override.

### Frontend

- Create: `frontend/src/components/review-queue/review-queue-shared.tsx`
  - Shared bucket labels, shared cards, shared row rendering, shared timestamp helpers.
- Create: `frontend/src/app/review/queue/[bucket]/page.tsx`
  - Learner bucket detail page.
- Create: `frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx`
  - Learner bucket detail page tests.
- Modify: `frontend/src/app/review/queue/page.tsx`
  - Convert from flat grouped list to summary list of queue buckets.
- Modify: `frontend/src/app/review/queue/__tests__/page.test.tsx`
  - Update learner summary tests for bucket cards and open actions.
- Create: `frontend/src/app/admin/review-queue/[bucket]/page.tsx`
  - Admin bucket detail page.
- Create: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`
  - Admin bucket detail page tests.
- Modify: `frontend/src/app/admin/review-queue/page.tsx`
  - Convert from flat grouped list to summary list built on shared components.
- Modify: `frontend/src/app/admin/review-queue/__tests__/page.test.tsx`
  - Update admin summary tests.
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
  - Display exact scheduled time as source of truth and move manual override into explicit change control.
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
  - Add regression coverage for queue/detail schedule consistency.
- Modify: `frontend/src/lib/knowledge-map-client.ts`
  - Add summary/detail queue contract types and fetchers.
- Modify: `frontend/src/lib/auth-nav.tsx`
  - Change `Review` link to `View Review Queue` and target `/review/queue`.

### Seeds / E2E / Docs

- Modify: `scripts/seed_review_scenarios.py`
  - Ensure deterministic seed support for `admin@admin.com`.
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
  - Add deterministic summary/detail bucket seed shapes plus long-horizon progression fixtures.
- Create: `e2e/tests/full/user-review-queue-architecture.full.spec.ts`
  - Learner/admin summary/detail queue scenarios.
- Modify: `e2e/tests/full/user-review-queue-srs.full.spec.ts`
  - Expand toward long-horizon advancement and schedule-consistency assertions if still useful.
- Modify: `.github/workflows/ci.yml`
  - Run the new required review queue architecture scenario lane.
- Modify: `e2e/package.json`
  - Add/update review queue architecture CI command.
- Modify: `docs/status/project-status.md`
  - Record the new queue architecture and verification evidence.

## Task 1: Add RED Tests for Shared Queue Summary/Detail Contracts

**Files:**
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write failing unit tests for summary/detail queue projections**

```python
def test_build_grouped_review_queue_summary_returns_bucket_cards(...):
    ...

def test_build_review_queue_bucket_detail_sorts_by_next_review_ascending(...):
    ...

def test_build_current_schedule_payload_uses_actual_due_time_for_display(...):
    ...

def test_long_horizon_success_sequence_reaches_multi_month_bucket(...):
    ...
```

- [ ] **Step 2: Run the targeted backend tests to verify RED**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k 'grouped_review_queue or schedule_payload or long_horizon' -q`

Expected: FAIL with missing summary/detail helpers, missing API contracts, or schedule-payload assertion failures.

- [ ] **Step 3: Write failing API tests for learner/admin summary and bucket detail routes**

```python
async def test_get_review_queue_summary_success(...):
    ...

async def test_get_review_queue_bucket_detail_supports_sort_and_order(...):
    ...

async def test_get_admin_review_queue_bucket_detail_applies_effective_now(...):
    ...
```

- [ ] **Step 4: Run the targeted API tests to verify RED**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_api.py -k 'review_queue_summary or review_queue_bucket' -q`

Expected: FAIL because the new endpoints or response shapes do not exist yet.

## Task 2: Implement Shared Backend Queue Summary/Detail Projections

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/api/reviews.py`

- [ ] **Step 1: Add summary/detail queue projection helpers in the review service**

```python
async def get_grouped_review_queue_summary(...):
    ...

async def get_grouped_review_queue_bucket_detail(...):
    ...
```

- [ ] **Step 2: Add deterministic sorting and ordering support for bucket detail**

```python
ALLOWED_QUEUE_SORTS = {"next_review_at", "last_reviewed_at", "text"}
ALLOWED_QUEUE_ORDERS = {"asc", "desc"}
```

- [ ] **Step 3: Add learner/admin API endpoints for summary and bucket detail**

```python
@router.get("/queue/summary", ...)
@router.get("/queue/buckets/{bucket}", ...)
@router.get("/admin/queue/summary", ...)
@router.get("/admin/queue/buckets/{bucket}", ...)
```

- [ ] **Step 4: Harmonize current schedule payload with actual due timestamps**

```python
def _build_current_schedule_payload(...):
    return {
        "queue_item_id": ...,
        "next_review_at": due_at.isoformat() if due_at else None,
        "current_schedule_value": resolved_override_value,
        "current_schedule_label": resolved_override_label,
        "current_schedule_source": "scheduled_timestamp",
        ...
    }
```

- [ ] **Step 5: Run the targeted backend tests to verify GREEN**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -k 'grouped_review_queue or schedule_payload or long_horizon or review_queue_summary or review_queue_bucket' -q`

Expected: PASS

- [ ] **Step 6: Commit backend queue contract work**

```bash
git add backend/app/services/review.py backend/app/api/reviews.py backend/tests/test_review_service.py backend/tests/test_review_api.py
git commit -m "feat: add shared review queue summary and detail contracts"
```

## Task 3: Add RED Frontend Tests for Shared Queue Components and Bucket Pages

**Files:**
- Modify: `frontend/src/app/review/queue/__tests__/page.test.tsx`
- Modify: `frontend/src/app/admin/review-queue/__tests__/page.test.tsx`
- Create: `frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx`
- Create: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

- [ ] **Step 1: Rewrite learner summary tests to expect bucket cards instead of inline full item lists**

```tsx
expect(await screen.findByRole("link", { name: /open overdue queue/i })).toHaveAttribute(
  "href",
  "/review/queue/overdue",
);
```

- [ ] **Step 2: Add failing learner bucket-detail tests for sorting, ordering, and row actions**

```tsx
render(<ReviewQueueBucketPage params={...} searchParams={...} />);
expect(await screen.findByRole("heading", { name: /tomorrow/i })).toBeInTheDocument();
expect(screen.getByLabelText(/sort by/i)).toBeInTheDocument();
expect(screen.getByLabelText(/order/i)).toBeInTheDocument();
```

- [ ] **Step 3: Add failing admin summary/detail tests for debug fields plus bucket drill-in**

```tsx
expect(await screen.findByRole("link", { name: /open due now queue/i })).toHaveAttribute(
  "href",
  "/admin/review-queue/due_now",
);
```

- [ ] **Step 4: Add failing detail-page regression tests for exact scheduled timestamp display**

```tsx
expect(await screen.findByText(/scheduled for apr 6, 2026/i)).toBeInTheDocument();
expect(screen.getByLabelText(/change next review/i)).toBeInTheDocument();
```

- [ ] **Step 5: Run targeted frontend tests to verify RED**

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/review/queue/__tests__/page.test.tsx' 'src/app/review/queue/[bucket]/__tests__/page.test.tsx' 'src/app/admin/review-queue/__tests__/page.test.tsx' 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx' 'src/components/__tests__/knowledge-entry-detail-page.test.tsx'`

Expected: FAIL because the shared queue components, drill-in pages, and harmonized detail UI do not exist yet.

## Task 4: Implement Shared Frontend Review Queue Module and Learner/Admin Summary Pages

**Files:**
- Create: `frontend/src/components/review-queue/review-queue-shared.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/app/review/queue/page.tsx`
- Modify: `frontend/src/app/admin/review-queue/page.tsx`
- Modify: `frontend/src/app/review/queue/__tests__/page.test.tsx`
- Modify: `frontend/src/app/admin/review-queue/__tests__/page.test.tsx`
- Modify: `frontend/src/lib/auth-nav.tsx`

- [ ] **Step 1: Add summary/detail client contracts and fetch helpers**

```ts
export type ReviewQueueSummaryResponse = ...
export type ReviewQueueBucketDetailResponse = ...
export const getReviewQueueSummary = ...
export const getReviewQueueBucketDetail = ...
```

- [ ] **Step 2: Create shared queue rendering helpers and components**

```tsx
export function ReviewQueueBucketSummaryCard(...) { ... }
export function ReviewQueueItemRow(...) { ... }
export function formatReviewQueueTimestamp(...) { ... }
```

- [ ] **Step 3: Replace learner summary page with bucket-summary cards**

```tsx
<Link href={`/review/queue/${group.bucket}`}>Open</Link>
```

- [ ] **Step 4: Replace admin summary page with the same shared summary components plus debug chrome**

```tsx
<Link href={`/admin/review-queue/${group.bucket}${query}`}>Open</Link>
```

- [ ] **Step 5: Rename top navigation review link**

```tsx
<Link href="/review/queue" data-testid="nav-review-link">
  View Review Queue
</Link>
```

- [ ] **Step 6: Run the targeted frontend tests to verify GREEN for summary pages**

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/review/queue/__tests__/page.test.tsx' 'src/app/admin/review-queue/__tests__/page.test.tsx'`

Expected: PASS

- [ ] **Step 7: Commit shared frontend queue summary work**

```bash
git add frontend/src/components/review-queue/review-queue-shared.tsx frontend/src/lib/knowledge-map-client.ts frontend/src/app/review/queue/page.tsx frontend/src/app/admin/review-queue/page.tsx frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/app/admin/review-queue/__tests__/page.test.tsx frontend/src/lib/auth-nav.tsx
git commit -m "feat: add shared review queue summary pages"
```

## Task 5: Implement Learner/Admin Bucket Detail Pages and Schedule Consistency UI

**Files:**
- Create: `frontend/src/app/review/queue/[bucket]/page.tsx`
- Create: `frontend/src/app/admin/review-queue/[bucket]/page.tsx`
- Create: `frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx`
- Create: `frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

- [ ] **Step 1: Implement learner bucket detail page**

```tsx
const sort = searchParams.sort ?? "next_review_at";
const order = searchParams.order ?? "asc";
```

- [ ] **Step 2: Implement admin bucket detail page with debug-only row fields**

```tsx
<DebugField label="next_due_at" value={item.next_due_at} />
```

- [ ] **Step 3: Update detail page review panel to show exact scheduled time first**

```tsx
<p>Scheduled for {formatReviewTimestamp(detailReviewQueue?.next_review_at)}</p>
<label htmlFor="detail-review-override">Change next review</label>
```

- [ ] **Step 4: Keep manual override selection behavior but present it as an override control**

```tsx
await updateReviewQueueSchedule(queueId, scheduleValue);
```

- [ ] **Step 5: Run the targeted frontend tests to verify GREEN**

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/review/queue/[bucket]/__tests__/page.test.tsx' 'src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx' 'src/components/__tests__/knowledge-entry-detail-page.test.tsx'`

Expected: PASS

- [ ] **Step 6: Run frontend lint**

Run: `npm --prefix frontend run lint`

Expected: PASS

- [ ] **Step 7: Commit bucket detail pages and schedule UI harmonization**

```bash
git add frontend/src/app/review/queue/[bucket]/page.tsx frontend/src/app/admin/review-queue/[bucket]/page.tsx frontend/src/app/review/queue/[bucket]/__tests__/page.test.tsx frontend/src/app/admin/review-queue/[bucket]/__tests__/page.test.tsx frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx
git commit -m "feat: add review queue bucket pages and harmonize detail scheduling"
```

## Task 6: Seed Admin Review Data and Add Full E2E/CI Coverage

**Files:**
- Modify: `scripts/seed_review_scenarios.py`
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
- Create: `e2e/tests/full/user-review-queue-architecture.full.spec.ts`
- Modify: `e2e/tests/full/user-review-queue-srs.full.spec.ts`
- Modify: `e2e/package.json`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add deterministic admin manual seeding support**

```python
parser.add_argument("--email", action="append", ...)
# allow explicit --email admin@admin.com
```

- [ ] **Step 2: Add deterministic bucket-summary/detail and long-horizon E2E fixtures**

```ts
export async function seedAdminReviewQueueFixture(...) { ... }
export async function seedLongHorizonReviewFixture(...) { ... }
```

- [ ] **Step 3: Write full Playwright scenario for learner/admin queue architecture**

```ts
test("learner summary opens bucket detail and preserves sort/order", async () => { ... });
test("admin queue detail shows debug fields with effective_now override", async () => { ... });
test("repeated successful reviews advance work into long horizon buckets", async () => { ... });
```

- [ ] **Step 4: Run the new E2E file to verify RED if written before fixture/code updates, then GREEN after implementation**

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_ADMIN_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-architecture.full.spec.ts --project=chromium`

Expected: PASS after fixture and route implementation.

- [ ] **Step 5: Wire the new scenario into CI**

```json
"test:review:ci": "playwright test tests/full/user-review-queue-srs.full.spec.ts tests/full/user-review-queue-architecture.full.spec.ts ..."
```

- [ ] **Step 6: Run review E2E CI command locally**

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_ADMIN_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword npm --prefix e2e run test:review:ci`

Expected: PASS

- [ ] **Step 7: Commit seed and E2E/CI coverage updates**

```bash
git add scripts/seed_review_scenarios.py e2e/tests/helpers/review-scenario-fixture.ts e2e/tests/full/user-review-queue-architecture.full.spec.ts e2e/tests/full/user-review-queue-srs.full.spec.ts e2e/package.json .github/workflows/ci.yml
git commit -m "test: cover review queue architecture and long-horizon SRS"
```

## Task 7: Update Status and Run Final Verification

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `docs/superpowers/plans/2026-04-05-review-queue-architecture-and-schedule-harmonization-plan.md`

- [ ] **Step 1: Update project status with the new architecture and evidence**

```md
| 2026-04-05 | Review queue now uses shared learner/admin summary+detail architecture ... | Codex | ... |
```

- [ ] **Step 2: Mark completed plan items in this file**

```md
- [x] ...
```

- [ ] **Step 3: Run backend verification**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q`

Expected: PASS

- [ ] **Step 4: Run frontend verification**

Run: `npm --prefix frontend run test:review`

Expected: PASS

- [ ] **Step 5: Run lint and diff checks**

Run: `npm --prefix frontend run lint`

Expected: PASS

Run: `git -C /Users/johnson/AI/src/words-v2/.worktrees/review_entry_state_cutover_20260404 diff --check`

Expected: PASS

- [ ] **Step 6: Commit docs/status updates**

```bash
git add docs/status/project-status.md docs/superpowers/plans/2026-04-05-review-queue-architecture-and-schedule-harmonization-plan.md
git commit -m "docs: record review queue architecture rollout"
```
