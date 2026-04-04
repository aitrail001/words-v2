# SRS Queue Visibility and Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a learner-facing SRS queue page, an admin/debug SRS queue page with time-travel inspection, and full review/SRS scenario coverage across unit, API, E2E, and CI.

**Architecture:** Extend the existing review service with a single grouped queue projection and deterministic bucket classifier, then expose it through learner and admin-facing API shapes. Reuse that shared projection in two frontend pages: a normal learner queue page and an admin/debug queue page with effective-time override. Back the feature with frozen-time scheduler tests, grouped-queue API tests, real scenario Playwright flows, and explicit CI coverage.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React/Next.js App Router, Testing Library, Playwright, GitHub Actions

---

## File Structure

**Create:**
- `frontend/src/app/review/queue/page.tsx` — learner-facing grouped review queue page
- `frontend/src/app/review/queue/__tests__/page.test.tsx` — learner queue page unit tests
- `frontend/src/app/admin/review-queue/page.tsx` — admin/debug grouped review queue page with time override
- `frontend/src/app/admin/review-queue/__tests__/page.test.tsx` — admin/debug page unit tests
- `e2e/tests/full/user-review-queue-srs.full.spec.ts` — learner + admin scenario coverage for grouped queue and time travel

**Modify:**
- `backend/app/services/review.py` — add grouped queue projection, bucket classifier, and effective-time support
- `backend/app/api/reviews.py` — expose learner-facing queue endpoint and admin/debug queue endpoint
- `backend/tests/test_review_service.py` — frozen-time scheduler and bucket-classification tests
- `backend/tests/test_review_api.py` — grouped queue API and time-override tests
- `frontend/src/app/page.tsx` — add `View Review Queue` learner action on the home review card
- `frontend/src/app/__tests__/page.test.tsx` — assert home-page queue navigation
- `frontend/src/lib/knowledge-map-client.ts` — add typed client methods for learner/admin queue pages
- `e2e/tests/helpers/review-scenario-fixture.ts` — seed deterministic grouped queue states across multiple time buckets
- `.github/workflows/ci.yml` — add/expand explicit review/SRS scenario coverage
- `docs/status/project-status.md` — record final scope and verification evidence

---

### Task 1: Backend Bucket Classifier and Grouped Queue Projection

**Files:**
- Modify: `backend/app/services/review.py`
- Test: `backend/tests/test_review_service.py`

- [ ] **Step 1: Write the failing unit tests for bucket classification and queue projection**

```python
from datetime import UTC, datetime, timedelta
import uuid

from app.models.entry_review import EntryReviewState


async def test_group_queue_items_buckets_states_by_due_window(db_session, review_service):
    now = datetime(2026, 4, 5, 9, 0, tzinfo=UTC)
    user_id = uuid.uuid4()

    overdue = EntryReviewState(
        user_id=user_id,
        entry_type="word",
        entry_id=uuid.uuid4(),
        target_type="word",
        target_id=uuid.uuid4(),
        next_due_at=now - timedelta(hours=2),
    )
    tomorrow = EntryReviewState(
        user_id=user_id,
        entry_type="word",
        entry_id=uuid.uuid4(),
        target_type="word",
        target_id=uuid.uuid4(),
        next_due_at=now + timedelta(days=1, hours=1),
    )
    db_session.add_all([overdue, tomorrow])
    await db_session.commit()

    payload = await review_service.get_grouped_review_queue(user_id=user_id, now=now)

    assert payload["total_count"] == 2
    assert payload["groups"][0]["bucket"] == "overdue"
    assert payload["groups"][1]["bucket"] == "tomorrow"


async def test_group_queue_items_excludes_known_and_to_learn_entries(
    db_session,
    review_service,
    learner_status_factory,
):
    ...


def test_classify_review_bucket_handles_exact_boundaries():
    now = datetime(2026, 4, 5, 9, 0, tzinfo=UTC)

    assert ReviewService.classify_review_bucket(now - timedelta(seconds=1), now) == "overdue"
    assert ReviewService.classify_review_bucket(now, now) == "due_now"
    assert ReviewService.classify_review_bucket(now + timedelta(days=95), now) == "three_to_six_months"
```

- [ ] **Step 2: Run the targeted backend tests to verify RED**

Run:
```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py -k "group_queue_items or classify_review_bucket" -q
```

Expected:
```text
FAIL
```

- [ ] **Step 3: Implement the minimal bucket classifier and grouped queue projection**

```python
@dataclass(frozen=True)
class GroupedReviewQueueItem:
    queue_item_id: str
    entry_id: str
    entry_type: str
    text: str
    status: str
    next_review_at: str | None
    last_reviewed_at: str | None


class ReviewService:
    @classmethod
    def classify_review_bucket(cls, due_at: datetime | None, now: datetime) -> str:
        if due_at is None or due_at <= now - timedelta(seconds=1):
            return "overdue"
        if due_at <= now:
            return "due_now"
        if due_at.date() == now.date():
            return "later_today"
        if due_at.date() == (now + timedelta(days=1)).date():
            return "tomorrow"
        if due_at <= now + timedelta(days=7):
            return "this_week"
        if due_at <= now + timedelta(days=31):
            return "this_month"
        if due_at <= now + timedelta(days=92):
            return "one_to_three_months"
        if due_at <= now + timedelta(days=183):
            return "three_to_six_months"
        return "six_plus_months"

    async def get_grouped_review_queue(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        include_debug_fields: bool = False,
    ) -> dict[str, Any]:
        states = await self._list_active_queue_states(user_id=user_id, now=now)
        groups: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in REVIEW_BUCKET_ORDER}
        for state in states:
            bucket = self.classify_review_bucket(state.recheck_due_at or state.next_due_at, now)
            groups[bucket].append(self._serialize_grouped_queue_row(state, include_debug_fields=include_debug_fields))
        return {
            "generated_at": now.isoformat(),
            "total_count": sum(len(items) for items in groups.values()),
            "groups": [
                {"bucket": bucket, "count": len(groups[bucket]), "items": groups[bucket]}
                for bucket in REVIEW_BUCKET_ORDER
                if groups[bucket]
            ],
        }
```

- [ ] **Step 4: Run the same targeted backend tests to verify GREEN**

Run:
```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py -k "group_queue_items or classify_review_bucket" -q
```

Expected:
```text
PASS
```

- [ ] **Step 5: Commit the backend bucketing slice**

```bash
git add backend/app/services/review.py backend/tests/test_review_service.py
git commit -m "feat: add grouped SRS queue projection"
```

---

### Task 2: Learner and Admin Queue API Contracts

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`
- Test: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write the failing API tests for learner queue and admin time-travel queue**

```python
def test_get_review_queue_groups_items_by_bucket(client, auth_headers, seeded_review_queue_states):
    response = client.get("/api/reviews/queue/grouped", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_count"] >= 1
    assert payload["groups"][0]["bucket"] in {"overdue", "due_now", "later_today", "tomorrow"}


def test_get_review_queue_grouped_excludes_to_learn(client, auth_headers, seeded_to_learn_state):
    response = client.get("/api/reviews/queue/grouped", headers=auth_headers)

    payload = response.json()
    item_ids = {
        item["entry_id"]
        for group in payload["groups"]
        for item in group["items"]
    }
    assert str(seeded_to_learn_state.entry_id) not in item_ids


def test_admin_review_queue_grouped_supports_effective_time_override(
    admin_client,
    admin_auth_headers,
    seeded_future_review_state,
):
    response = admin_client.get(
        "/api/reviews/admin/queue/grouped",
        params={"effective_now": "2026-10-05T09:00:00+00:00"},
        headers=admin_auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["debug"]["effective_now"] == "2026-10-05T09:00:00+00:00"
```

- [ ] **Step 2: Run the targeted API tests to verify RED**

Run:
```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_api.py -k "grouped queue" -q
```

Expected:
```text
FAIL
```

- [ ] **Step 3: Implement the minimal learner and admin endpoints**

```python
@router.get("/queue/grouped")
async def get_grouped_review_queue(
    current_user: User = Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    return await review_service.get_grouped_review_queue(
        user_id=current_user.id,
        now=now,
        include_debug_fields=False,
    )


@router.get("/admin/queue/grouped")
async def get_grouped_review_queue_admin(
    effective_now: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    review_service: ReviewService = Depends(get_review_service),
) -> dict[str, Any]:
    now = effective_now or datetime.now(UTC)
    payload = await review_service.get_grouped_review_queue(
        user_id=current_user.id,
        now=now,
        include_debug_fields=True,
    )
    payload["debug"] = {"effective_now": now.isoformat()}
    return payload
```

- [ ] **Step 4: Run the targeted API tests to verify GREEN**

Run:
```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_api.py -k "grouped queue" -q
```

Expected:
```text
PASS
```

- [ ] **Step 5: Commit the API contract slice**

```bash
git add backend/app/api/reviews.py backend/app/services/review.py backend/tests/test_review_api.py
git commit -m "feat: expose learner and admin SRS queue APIs"
```

---

### Task 3: Learner Queue Page and Home Navigation

**Files:**
- Create: `frontend/src/app/review/queue/page.tsx`
- Create: `frontend/src/app/review/queue/__tests__/page.test.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/__tests__/page.test.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts`

- [ ] **Step 1: Write the failing frontend tests for learner queue rendering and home-page navigation**

```tsx
it("shows View Review Queue on the home review card", async () => {
  render(await HomePage())

  expect(screen.getByRole("link", { name: /view review queue/i })).toHaveAttribute(
    "href",
    "/review/queue",
  )
})


it("renders grouped learner queue buckets and start-review links", async () => {
  mockedGetGroupedReviewQueue.mockResolvedValue({
    total_count: 2,
    groups: [
      {
        bucket: "due_now",
        count: 1,
        items: [{ queue_item_id: "queue-1", text: "persistence", entry_type: "word", status: "learning", next_review_at: "2026-04-05T09:00:00+00:00" }],
      },
    ],
  })

  render(await ReviewQueuePage())

  expect(screen.getByRole("heading", { name: /due now/i })).toBeInTheDocument()
  expect(screen.getByRole("link", { name: /review persistence/i })).toHaveAttribute(
    "href",
    "/review?queue_item_id=queue-1",
  )
})
```

- [ ] **Step 2: Run the targeted frontend tests to verify RED**

Run:
```bash
npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/__tests__/page.test.tsx' 'src/app/review/queue/__tests__/page.test.tsx'
```

Expected:
```text
FAIL
```

- [ ] **Step 3: Implement the learner queue client and page**

```tsx
export interface GroupedReviewQueueResponse {
  total_count: number
  groups: Array<{
    bucket: string
    count: number
    items: Array<{
      queue_item_id: string
      entry_id: string
      entry_type: "word" | "phrase"
      text: string
      status: string
      next_review_at: string | null
      last_reviewed_at: string | null
    }>
  }>
}

export async function getGroupedReviewQueue(): Promise<GroupedReviewQueueResponse> {
  return apiClient.get("/reviews/queue/grouped")
}
```

```tsx
export default async function ReviewQueuePage() {
  const queue = await getGroupedReviewQueue()

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold">Review Queue</h1>
        <p className="mt-2 text-sm text-slate-600">{queue.total_count} scheduled review items</p>
      </header>
      {queue.groups.map((group) => (
        <section key={group.bucket} className="mb-8">
          <h2 className="text-xl font-semibold">{formatBucketLabel(group.bucket)}</h2>
          <ul className="mt-4 space-y-3">
            {group.items.map((item) => (
              <li key={item.queue_item_id} className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-semibold">{item.text}</p>
                    <p className="text-sm text-slate-600">{formatNextReview(item.next_review_at)}</p>
                  </div>
                  <div className="flex gap-3">
                    <Link href={`/${item.entry_type}/${item.entry_id}`}>Open detail</Link>
                    <Link aria-label={`Review ${item.text}`} href={`/review?queue_item_id=${encodeURIComponent(item.queue_item_id)}`}>
                      Start review
                    </Link>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  )
}
```

- [ ] **Step 4: Run the targeted frontend tests to verify GREEN**

Run:
```bash
npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/__tests__/page.test.tsx' 'src/app/review/queue/__tests__/page.test.tsx'
```

Expected:
```text
PASS
```

- [ ] **Step 5: Commit the learner UI slice**

```bash
git add frontend/src/app/page.tsx frontend/src/app/__tests__/page.test.tsx frontend/src/app/review/queue/page.tsx frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/lib/knowledge-map-client.ts
git commit -m "feat: add learner SRS queue page"
```

---

### Task 4: Admin Debug Queue Page with Effective-Time Override

**Files:**
- Create: `frontend/src/app/admin/review-queue/page.tsx`
- Create: `frontend/src/app/admin/review-queue/__tests__/page.test.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts`

- [ ] **Step 1: Write the failing frontend tests for admin/debug SRS inspection**

```tsx
it("renders debug metadata and effective time controls", async () => {
  mockedGetAdminGroupedReviewQueue.mockResolvedValue({
    total_count: 1,
    debug: { effective_now: "2026-10-05T09:00:00+00:00" },
    groups: [
      {
        bucket: "due_now",
        count: 1,
        items: [{
          queue_item_id: "queue-1",
          text: "persistence",
          entry_type: "word",
          status: "learning",
          next_review_at: "2026-04-05T09:00:00+00:00",
          debug: { last_outcome: "passed", prompt_family: "confidence_check" },
        }],
      },
    ],
  })

  render(await AdminReviewQueuePage({ searchParams: Promise.resolve({ effective_now: "2026-10-05T09:00:00+00:00" }) }))

  expect(screen.getByDisplayValue("2026-10-05T09:00:00+00:00")).toBeInTheDocument()
  expect(screen.getByText(/confidence_check/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the targeted frontend tests to verify RED**

Run:
```bash
npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/admin/review-queue/__tests__/page.test.tsx'
```

Expected:
```text
FAIL
```

- [ ] **Step 3: Implement the admin/debug page and client**

```tsx
export async function getAdminGroupedReviewQueue(effectiveNow?: string): Promise<GroupedReviewQueueResponse> {
  const params = effectiveNow ? `?effective_now=${encodeURIComponent(effectiveNow)}` : ""
  return apiClient.get(`/reviews/admin/queue/grouped${params}`)
}
```

```tsx
export default async function AdminReviewQueuePage({
  searchParams,
}: {
  searchParams: Promise<{ effective_now?: string }>
}) {
  const { effective_now } = await searchParams
  const queue = await getAdminGroupedReviewQueue(effective_now)

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-semibold">SRS Queue Debug</h1>
      <form className="mt-6 flex items-end gap-3" method="get">
        <label className="flex flex-col gap-2 text-sm font-medium">
          Effective now
          <input name="effective_now" defaultValue={queue.debug?.effective_now ?? ""} className="rounded-md border px-3 py-2" />
        </label>
        <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-white">Apply</button>
      </form>
      {queue.groups.map((group) => (
        <section key={group.bucket} className="mt-8">
          <h2 className="text-xl font-semibold">{formatBucketLabel(group.bucket)}</h2>
          {group.items.map((item) => (
            <article key={item.queue_item_id} className="mt-3 rounded-xl border border-slate-200 p-4">
              <p className="font-semibold">{item.text}</p>
              <p className="text-sm text-slate-600">next_review_at: {item.next_review_at ?? "none"}</p>
              <p className="text-sm text-slate-600">prompt_family: {item.debug?.prompt_family ?? "unknown"}</p>
            </article>
          ))}
        </section>
      ))}
    </main>
  )
}
```

- [ ] **Step 4: Run the targeted frontend tests to verify GREEN**

Run:
```bash
npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/admin/review-queue/__tests__/page.test.tsx'
```

Expected:
```text
PASS
```

- [ ] **Step 5: Commit the admin/debug UI slice**

```bash
git add frontend/src/app/admin/review-queue/page.tsx frontend/src/app/admin/review-queue/__tests__/page.test.tsx frontend/src/lib/knowledge-map-client.ts
git commit -m "feat: add admin SRS queue debug page"
```

---

### Task 5: Real Scenario E2E Coverage and CI Integration

**Files:**
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
- Create: `e2e/tests/full/user-review-queue-srs.full.spec.ts`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Write the failing E2E scenario and CI-target expectations**

```ts
test("learner queue page groups items and starting review from a row advances schedule", async ({ page }) => {
  await seedReviewScenarioFixture({
    email: "user@user.com",
    groupedQueue: [
      { term: "persistence", promptType: "confidence_check", dueOffsetHours: -1 },
      { term: "as it is", promptType: "audio_to_definition", dueOffsetDays: 1 },
      { term: "candidate", promptType: "speak_recall", dueOffsetDays: 120 },
    ],
  })

  await page.goto("/review/queue")
  await expect(page.getByRole("heading", { name: /overdue/i })).toBeVisible()
  await expect(page.getByRole("heading", { name: /tomorrow/i })).toBeVisible()
  await expect(page.getByRole("heading", { name: /3-6 months/i })).toBeVisible()

  await page.getByRole("link", { name: /review persistence/i }).click()
  await expect(page).toHaveURL(/\/review\?queue_item_id=/)
})


test("admin queue debug time travel moves a future item into due now", async ({ page }) => {
  await page.goto("/admin/review-queue?effective_now=2026-10-05T09:00:00+00:00")
  await expect(page.getByRole("heading", { name: /due now/i })).toBeVisible()
  await expect(page.getByText(/candidate/i)).toBeVisible()
})
```

- [ ] **Step 2: Run the new E2E target to verify RED**

Run:
```bash
E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts --project=chromium
```

Expected:
```text
FAIL
```

- [ ] **Step 3: Implement deterministic fixture support and CI lane**

```ts
export async function seedGroupedReviewQueueScenario(options: {
  email: string
  groupedQueue: Array<{
    term: string
    promptType: string
    dueOffsetHours?: number
    dueOffsetDays?: number
  }>
}): Promise<void> {
  // Seed real entry-review states with stable due timestamps and prompt overrides.
}
```

```yaml
- name: Review/SRS full scenario lane
  run: >
    E2E_API_URL=http://127.0.0.1:8000/api
    E2E_BASE_URL=http://127.0.0.1:3000
    PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000
    E2E_DB_PASSWORD=devpassword
    pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts --project=chromium
```

- [ ] **Step 4: Run the full changed-scope verification to verify GREEN**

Run:
```bash
PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q
npm --prefix frontend test -- --runInBand --runTestsByPath 'src/app/__tests__/page.test.tsx' 'src/app/review/queue/__tests__/page.test.tsx' 'src/app/admin/review-queue/__tests__/page.test.tsx'
npm --prefix frontend run lint
E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts --project=chromium
git diff --check
```

Expected:
```text
PASS
```

- [ ] **Step 5: Update status board and commit the final SRS visibility/testing slice**

```markdown
Add a `2026-04-05` status change entry to `docs/status/project-status.md` summarizing:
- learner review queue page
- admin SRS debug page
- effective-time QA support
- real scenario review/SRS E2E and CI coverage
- exact verification commands and pass counts
```

```bash
git add e2e/tests/helpers/review-scenario-fixture.ts e2e/tests/full/user-review-queue-srs.full.spec.ts .github/workflows/ci.yml docs/status/project-status.md
git commit -m "feat: add SRS queue visibility and scenario coverage"
```
