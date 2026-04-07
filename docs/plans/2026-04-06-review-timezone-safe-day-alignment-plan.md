# Timezone-Safe Review Day Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw timestamp-based official review scheduling with timezone-safe review-day alignment so due items unlock together at one local release hour and never unlock early after timezone changes.

**Architecture:** Introduce one backend scheduling module as the single source of truth for review-day math, persist `due_review_date` and `min_due_at_utc` on `entry_review_states`, add authoritative user timezone storage on `user_preferences`, then migrate queue/submission/detail/frontend behavior to consume the new schedule model. Keep same-session retry separate from official scheduling and remove active dependency on the old raw-hour due model after rollout.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, Next.js/React, Jest, Playwright, PostgreSQL

---

## File Map

### Backend Scheduling Core

- Create: `backend/app/services/review_schedule.py`
  - Single source of truth for review-day calculations
  - Effective review date
  - Bucket day offsets
  - Local release instant to UTC conversion
  - Dual due check
  - Sticky due helpers
- Modify: `backend/app/services/review.py`
  - Replace raw `next_due_at` / `timedelta(days=...)` scheduling logic
  - Move queue due filters and bucket summaries to the new scheduling layer
- Modify: `backend/app/services/review_submission.py`
  - Replace `calculate_next_review(...).next_review` as the official due source
  - Keep same-session retry on `recheck_due_at` only
- Modify: `backend/app/models/entry_review.py`
  - Add `due_review_date`
  - Add `min_due_at_utc`
  - Keep temporary `next_due_at` compatibility field during rollout
- Modify: `backend/app/models/user_preference.py`
  - Add authoritative `timezone`

### Backend API

- Modify: `backend/app/api/user_preferences.py`
  - Read/write timezone
  - Validate IANA timezone format
- Modify: `backend/app/api/reviews.py`
  - Extend queue/detail/summary payloads with new schedule fields where needed

### Migrations

- Create: `backend/alembic/versions/<next>_add_timezone_safe_review_schedule.py`
  - Add `user_preferences.timezone`
  - Add `entry_review_states.due_review_date`
  - Add `entry_review_states.min_due_at_utc`
  - Backfill active review states from existing `next_due_at`

### Frontend

- Modify: `frontend/src/lib/user-preferences-client.ts`
  - Include timezone in the preferences contract
- Modify: `frontend/src/lib/knowledge-map-client.ts`
  - Extend review queue/detail schedule payload types
- Modify: `frontend/src/app/review/page.tsx`
  - Stop assuming raw timestamp-only official scheduling
- Modify: `frontend/src/app/review/queue/page.tsx`
  - Render due labels from server-backed review-day schedule
- Modify: `frontend/src/app/review/queue/[bucket]/page.tsx`
  - Show stage plus new due timing fields consistently
- Modify: `frontend/src/components/review-queue/review-queue-shared.tsx`
  - Shared due label presentation
- Modify: `frontend/src/components/review-queue/review-queue-utils.ts`
  - Queue formatting helpers only, no client-side schedule source-of-truth logic
- Modify: `frontend/src/components/knowledge-map-range-detail.tsx`
  - Show next review from review-day schedule fields
- Modify: `frontend/src/components/knowledge-map-range-detail.test.tsx`
  - Cover new schedule rendering
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
  - Cover timezone-safe next review rendering
- Modify: `frontend/src/app/settings/page.tsx`
  - Timezone display if needed for debug/visibility

### Tests

- Create: `backend/tests/test_review_schedule.py`
  - Unit tests for review-day math
- Modify: `backend/tests/test_review_service.py`
  - Queue due logic, sticky due, travel, manual override
- Modify: `backend/tests/test_review_api.py`
  - Queue/detail payloads and due semantics
- Modify: `backend/tests/test_user_preferences_api.py`
  - Timezone persistence and validation
- Modify: `frontend/src/lib/__tests__/user-preferences-client.test.ts`
  - Preferences payload shape with timezone
- Modify: `frontend/src/lib/__tests__/knowledge-map-client.test.ts`
  - Queue/detail schedule fields
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
  - Review page behavior with new schedule fields
- Modify: `frontend/src/app/review/queue/__tests__/page.test.tsx`
  - Queue labels and grouping
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
  - Deterministic seeded schedule scenarios with timezone support
- Modify: `e2e/tests/full/user-review-queue-srs.full.spec.ts`
  - Same-day alignment, sticky due, travel, due rendering
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`
  - Learn/review flows under the new schedule model

### Documentation

- Modify: `docs/status/project-status.md`
  - Record implementation and verification evidence

---

## Task 1: Add Scheduling Core Unit Tests

**Files:**
- Create: `backend/tests/test_review_schedule.py`
- Modify: `backend/app/services/review_schedule.py`

- [ ] **Step 1: Write failing unit tests for effective review date and bucket release alignment**

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.review_schedule import (
    REVIEW_RELEASE_HOUR_LOCAL,
    bucket_days,
    effective_review_date,
    min_due_at_for_bucket,
)


def test_effective_review_date_uses_previous_calendar_day_before_release_hour() -> None:
    instant = datetime(2026, 4, 10, 15, 30, tzinfo=timezone.utc)
    assert effective_review_date(
        instant_utc=instant,
        user_timezone="Australia/Melbourne",
        release_hour_local=REVIEW_RELEASE_HOUR_LOCAL,
    ).isoformat() == "2026-04-10"


def test_min_due_at_aligns_multiple_reviews_to_same_release_time() -> None:
    morning_review = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    late_review = datetime(2026, 4, 10, 12, 30, tzinfo=timezone.utc)

    first = min_due_at_for_bucket(
        reviewed_at_utc=morning_review,
        user_timezone="Australia/Melbourne",
        bucket="3d",
        release_hour_local=REVIEW_RELEASE_HOUR_LOCAL,
    )
    second = min_due_at_for_bucket(
        reviewed_at_utc=late_review,
        user_timezone="Australia/Melbourne",
        bucket="3d",
        release_hour_local=REVIEW_RELEASE_HOUR_LOCAL,
    )

    assert first == second
    assert first.astimezone(ZoneInfo("Australia/Melbourne")).hour == REVIEW_RELEASE_HOUR_LOCAL


def test_bucket_days_maps_known_bucket_to_none() -> None:
    assert bucket_days("Known") is None
```

- [ ] **Step 2: Run the new scheduling tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_schedule.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing functions in `app.services.review_schedule`.

- [ ] **Step 3: Write the minimal scheduling module**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


REVIEW_RELEASE_HOUR_LOCAL = 4
BUCKET_DAY_OFFSETS = {
    "1d": 1,
    "2d": 2,
    "3d": 3,
    "5d": 5,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
    "180d": 180,
    "Known": None,
}


def bucket_days(bucket: str) -> int | None:
    return BUCKET_DAY_OFFSETS[bucket]


def effective_review_date(
    *,
    instant_utc: datetime,
    user_timezone: str,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> date:
    local_instant = instant_utc.astimezone(ZoneInfo(user_timezone))
    local_date = local_instant.date()
    if local_instant.hour < release_hour_local:
        return local_date - timedelta(days=1)
    return local_date


def min_due_at_for_bucket(
    *,
    reviewed_at_utc: datetime,
    user_timezone: str,
    bucket: str,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> datetime | None:
    offset_days = bucket_days(bucket)
    if offset_days is None:
        return None
    review_day = effective_review_date(
        instant_utc=reviewed_at_utc,
        user_timezone=user_timezone,
        release_hour_local=release_hour_local,
    )
    due_review_day = review_day + timedelta(days=offset_days)
    local_due = datetime.combine(
        due_review_day,
        time(hour=release_hour_local),
        tzinfo=ZoneInfo(user_timezone),
    )
    return local_due.astimezone(timezone.utc)
```

- [ ] **Step 4: Run the scheduling tests to verify GREEN**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_schedule.py -q`

Expected: PASS.

- [ ] **Step 5: Expand the unit tests to cover travel, sticky due primitives, and DST**

```python
from datetime import date, datetime, timezone

from app.services.review_schedule import (
    due_now,
    due_review_date_for_bucket,
    sticky_due,
)


def test_due_now_requires_both_review_day_and_min_due_at() -> None:
    assert due_now(
        now_utc=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        user_timezone="Australia/Melbourne",
        due_review_date=date(2026, 4, 11),
        min_due_at_utc=datetime(2026, 4, 10, 16, 0, tzinfo=timezone.utc),
    ) is False


def test_sticky_due_stays_true_once_card_has_become_due() -> None:
    assert sticky_due(
        already_due=True,
        dynamically_due=False,
    ) is True


def test_dst_boundary_keeps_local_release_hour() -> None:
    scheduled = min_due_at_for_bucket(
        reviewed_at_utc=datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc),
        user_timezone="Australia/Melbourne",
        bucket="1d",
    )
    assert scheduled is not None
    assert scheduled.astimezone(ZoneInfo("Australia/Melbourne")).hour == 4
```

- [ ] **Step 6: Run the expanded test file**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_schedule.py -q`

Expected: PASS with DST, sticky-due, and dual due checks covered.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/review_schedule.py backend/tests/test_review_schedule.py
git commit -m "test: add timezone-safe review scheduling core"
```

**Acceptance Criteria:**
- Scheduling math exists in one backend module.
- Effective review date uses the 04:00 boundary.
- Bucket scheduling aligns same-day reviews to one release instant.
- Unit coverage includes dual due logic, DST, and sticky due primitives.

---

## Task 2: Add Schema Fields And Backfill Migration

**Files:**
- Modify: `backend/app/models/entry_review.py`
- Modify: `backend/app/models/user_preference.py`
- Create: `backend/alembic/versions/<next>_add_timezone_safe_review_schedule.py`
- Modify: `backend/tests/test_user_preferences_api.py`
- Modify: `backend/tests/test_review_service.py`

- [ ] **Step 1: Write failing tests for timezone persistence and migrated schedule fields**

```python
def test_get_user_preferences_returns_timezone(client, auth_headers):
    response = client.get("/api/user-preferences", headers=auth_headers)
    assert response.status_code == 200
    assert "timezone" in response.json()


async def test_review_state_exposes_due_review_date_and_min_due_at(db_session, review_state):
    assert review_state.due_review_date is not None
    assert review_state.min_due_at_utc is not None
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_user_preferences_api.py backend/tests/test_review_service.py -q -k "timezone or due_review_date or min_due_at_utc"`

Expected: FAIL because the fields do not exist yet.

- [ ] **Step 3: Add the SQLAlchemy fields**

```python
from sqlalchemy import Date

due_review_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
min_due_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
```

```python
timezone: Mapped[str] = mapped_column(String(64), nullable=False, insert_default="UTC", server_default=text("'UTC'"))
```

- [ ] **Step 4: Write the Alembic migration with backfill**

```python
def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"))
    op.add_column("entry_review_states", sa.Column("due_review_date", sa.Date(), nullable=True))
    op.add_column("entry_review_states", sa.Column("min_due_at_utc", sa.DateTime(timezone=True), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT ers.id, ers.next_due_at, COALESCE(up.timezone, 'UTC') AS timezone
        FROM entry_review_states ers
        LEFT JOIN user_preferences up ON up.user_id = ers.user_id
        WHERE ers.next_due_at IS NOT NULL
    """)).mappings()
    for row in rows:
        min_due_at_utc = row["next_due_at"]
        due_review_date = derive_due_review_date(min_due_at_utc, row["timezone"])
        conn.execute(
            sa.text("""
                UPDATE entry_review_states
                SET min_due_at_utc = :min_due_at_utc,
                    due_review_date = :due_review_date
                WHERE id = :id
            """),
            {
                "id": row["id"],
                "min_due_at_utc": min_due_at_utc,
                "due_review_date": due_review_date,
            },
        )
```

- [ ] **Step 5: Run the focused tests again**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_user_preferences_api.py backend/tests/test_review_service.py -q -k "timezone or due_review_date or min_due_at_utc"`

Expected: PASS.

- [ ] **Step 6: Run the migration-specific sanity tests**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_user_preferences_api.py -q`

Expected: PASS with preferences payload including timezone.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/entry_review.py backend/app/models/user_preference.py backend/alembic/versions/*.py backend/tests/test_user_preferences_api.py backend/tests/test_review_service.py
git commit -m "feat: add timezone-safe review schedule fields"
```

**Acceptance Criteria:**
- Review states persist `due_review_date` and `min_due_at_utc`.
- User preferences persist authoritative IANA timezone.
- Migration backfills active rows without resetting buckets.
- Tests prove timezone is part of the API contract.

---

## Task 3: Migrate Submission Logic To Review-Day Scheduling

**Files:**
- Modify: `backend/app/services/review_submission.py`
- Modify: `backend/app/services/review.py`
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write failing service tests for success, fail, and manual override scheduling**

```python
async def test_success_schedules_from_effective_review_day_not_elapsed_hours(review_service, review_state):
    review_state.srs_bucket = "1d"
    result = await review_service.submit_queue_review(
        item_id=review_state.id,
        quality=5,
        time_spent_ms=1200,
        user_id=review_state.user_id,
        confirm=True,
        prompt_token=make_prompt_token(review_state),
        outcome="correct_tested",
    )
    assert result.due_review_date.isoformat() == "2026-04-11"


async def test_fail_sets_official_schedule_to_tomorrow_and_back_one_bucket(review_service, review_state):
    review_state.srs_bucket = "14d"
    result = await review_service.submit_queue_review(
        item_id=review_state.id,
        quality=0,
        time_spent_ms=1500,
        user_id=review_state.user_id,
        confirm=True,
        prompt_token=make_prompt_token(review_state),
        outcome="wrong",
    )
    assert result.srs_bucket == "7d"
    assert result.due_review_date.isoformat() == "2026-04-11"


async def test_manual_override_uses_review_day_alignment(review_service, review_state):
    result = await review_service.submit_queue_review(
        item_id=review_state.id,
        quality=5,
        time_spent_ms=900,
        user_id=review_state.user_id,
        confirm=True,
        prompt_token=make_prompt_token(review_state),
        outcome="correct_tested",
        schedule_override="7d",
    )
    assert result.srs_bucket == "7d"
    assert result.min_due_at_utc is not None
```

- [ ] **Step 2: Run the focused service/API tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q -k "effective_review_day or manual_override or back_one_bucket"`

Expected: FAIL because submit logic still uses raw timestamp scheduling.

- [ ] **Step 3: Replace official submit scheduling with the new scheduling module**

```python
reviewed_at = datetime.now(timezone.utc)
next_bucket = service._resolve_next_bucket(
    current_bucket=entry_state.srs_bucket,
    outcome=resolved_outcome,
    schedule_override=schedule_override,
    prompt_type=prompt_token_payload.get("prompt_type"),
)
due_review_date = due_review_date_for_bucket(
    reviewed_at_utc=reviewed_at,
    user_timezone=user_timezone,
    bucket=next_bucket,
)
min_due_at_utc = min_due_at_for_bucket(
    reviewed_at_utc=reviewed_at,
    user_timezone=user_timezone,
    bucket=next_bucket,
)
entry_state.srs_bucket = next_bucket
entry_state.due_review_date = due_review_date
entry_state.min_due_at_utc = min_due_at_utc
entry_state.next_due_at = min_due_at_utc
```

- [ ] **Step 4: Keep same-session retry separate**

```python
if resolved_outcome in {"lookup", "wrong"}:
    entry_state.recheck_due_at = reviewed_at + timedelta(minutes=10)
else:
    entry_state.recheck_due_at = None
```

- [ ] **Step 5: Run the focused tests again**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q -k "effective_review_day or manual_override or back_one_bucket"`

Expected: PASS.

- [ ] **Step 6: Run a broader review backend regression pass**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/review_submission.py backend/app/services/review.py backend/tests/test_review_service.py backend/tests/test_review_api.py
git commit -m "fix: schedule official reviews by local review day"
```

**Acceptance Criteria:**
- Official next review is derived from effective review date, not elapsed hours.
- Fail/back-one-bucket behavior remains V1-correct.
- Manual override resolves to aligned review-day release.
- Same-session retry stays separate from official scheduling.

---

## Task 4: Migrate Queue Due Logic And Sticky Due Behavior

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/tests/test_review_service.py`
- Modify: `backend/tests/test_review_api.py`

- [ ] **Step 1: Write failing tests for due queue, travel east/west, and sticky due**

```python
async def test_future_card_does_not_unlock_early_after_eastward_timezone_change(review_service, review_state):
    review_state.due_review_date = date(2026, 4, 11)
    review_state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
    items = await review_service.get_due_queue_items(review_state.user_id, now=datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc))
    assert review_state.id not in {item.id for item in items}


async def test_already_due_card_stays_due_after_timezone_change(review_service, review_state):
    review_state.due_review_date = date(2026, 4, 10)
    review_state.min_due_at_utc = datetime(2026, 4, 9, 18, 0, tzinfo=timezone.utc)
    review_state.last_due_check_timezone = "Australia/Melbourne"
    items = await review_service.get_due_queue_items(review_state.user_id, now=datetime(2026, 4, 10, 20, 0, tzinfo=timezone.utc))
    assert review_state.id in {item.id for item in items}
```

- [ ] **Step 2: Run the due-queue tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q -k "sticky_due or timezone_change or due_queue"`

Expected: FAIL because queue filters still use `next_due_at <= now` as the main official due rule.

- [ ] **Step 3: Replace raw due checks in `ReviewService`**

```python
def _is_state_officially_due(self, state: EntryReviewState, *, now: datetime, user_timezone: str) -> bool:
    dynamically_due = due_now(
        now_utc=now,
        user_timezone=user_timezone,
        due_review_date=state.due_review_date,
        min_due_at_utc=state.min_due_at_utc,
    )
    return sticky_due(
        already_due=self._has_state_become_due_before(state=state, now=now),
        dynamically_due=dynamically_due,
    )
```

- [ ] **Step 4: Update grouped queue responses to emit the new schedule fields**

```python
"due_review_date": state.due_review_date.isoformat() if state.due_review_date else None,
"min_due_at_utc": state.min_due_at_utc.isoformat() if state.min_due_at_utc else None,
"next_review_at": state.min_due_at_utc,
```

- [ ] **Step 5: Run the focused queue tests again**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py backend/tests/test_review_api.py -q -k "sticky_due or timezone_change or due_queue"`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/review.py backend/tests/test_review_service.py backend/tests/test_review_api.py
git commit -m "fix: make due queue timezone-safe and sticky"
```

**Acceptance Criteria:**
- Future cards do not unlock early after timezone updates.
- Already-due cards remain due until reviewed.
- Queue APIs expose schedule fields from the new model.
- Raw `next_due_at <= now` is no longer the source of truth for official due logic.

---

## Task 5: Add Timezone API Contract And Frontend Preference Sync

**Files:**
- Modify: `backend/app/api/user_preferences.py`
- Modify: `backend/tests/test_user_preferences_api.py`
- Modify: `frontend/src/lib/user-preferences-client.ts`
- Modify: `frontend/src/lib/__tests__/user-preferences-client.test.ts`
- Modify: `frontend/src/app/settings/page.tsx`

- [ ] **Step 1: Write failing backend and frontend preference tests**

```python
def test_put_user_preferences_accepts_timezone(client, auth_headers):
    response = client.put(
        "/api/user-preferences",
        headers=auth_headers,
        json={
            "accent_preference": "us",
            "translation_locale": "zh-Hans",
            "knowledge_view_preference": "cards",
            "show_translations_by_default": True,
            "review_depth_preset": "balanced",
            "enable_confidence_check": True,
            "enable_word_spelling": True,
            "enable_audio_spelling": False,
            "show_pictures_in_questions": False,
            "timezone": "Australia/Melbourne",
        },
    )
    assert response.status_code == 200
```

```typescript
it("sends timezone in the preferences payload", async () => {
  await updateUserPreferences({
    ...DEFAULT_USER_PREFERENCES,
    timezone: "Australia/Melbourne",
  });
  expect(apiClient.put).toHaveBeenCalledWith("/user-preferences", expect.objectContaining({
    timezone: "Australia/Melbourne",
  }));
});
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_user_preferences_api.py -q && npm --prefix frontend test -- --runInBand --runTestsByPath frontend/src/lib/__tests__/user-preferences-client.test.ts`

Expected: FAIL because timezone is not in either contract.

- [ ] **Step 3: Add timezone to API and client models**

```python
class UserPreferencesResponse(BaseModel):
    timezone: str
```

```typescript
export type UserPreferences = {
  ...
  timezone: string;
};
```

- [ ] **Step 4: Add timezone validation**

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

@field_validator("timezone")
@classmethod
def validate_timezone(cls, value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unsupported timezone") from exc
    return value
```

- [ ] **Step 5: Add client-side timezone sync hook-up**

```typescript
export const detectDeviceTimezone = (): string =>
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
```

```typescript
if (preferences.timezone !== detectDeviceTimezone()) {
  void updateUserPreferences({
    ...preferences,
    timezone: detectDeviceTimezone(),
  });
}
```

- [ ] **Step 6: Run the focused tests again**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_user_preferences_api.py -q && npm --prefix frontend test -- --runInBand --runTestsByPath frontend/src/lib/__tests__/user-preferences-client.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/user_preferences.py backend/tests/test_user_preferences_api.py frontend/src/lib/user-preferences-client.ts frontend/src/lib/__tests__/user-preferences-client.test.ts frontend/src/app/settings/page.tsx
git commit -m "feat: store authoritative learner timezone"
```

**Acceptance Criteria:**
- Preferences API reads/writes authoritative IANA timezone.
- Invalid timezones are rejected.
- Frontend contract includes timezone.
- Device timezone can auto-update the authoritative stored timezone.

---

## Task 6: Update Queue/Detail Frontend Rendering To Use The New Schedule Model

**Files:**
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/components/review-queue/review-queue-utils.ts`
- Modify: `frontend/src/components/review-queue/review-queue-shared.tsx`
- Modify: `frontend/src/app/review/queue/page.tsx`
- Modify: `frontend/src/app/review/queue/[bucket]/page.tsx`
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Modify: `frontend/src/app/review/queue/__tests__/page.test.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

- [ ] **Step 1: Write failing frontend tests for due label rendering from `due_review_date` / `min_due_at_utc`**

```typescript
it("renders queue items with due labels based on server-backed schedule fields", async () => {
  mockGroupedQueue({
    groups: [
      {
        bucket: "1d",
        count: 1,
        items: [
          {
            queue_item_id: "queue-1",
            entry_id: "word-1",
            entry_type: "word",
            text: "harbor",
            status: "learning",
            due_review_date: "2026-04-11",
            min_due_at_utc: "2026-04-10T18:00:00Z",
            next_review_at: "2026-04-10T18:00:00Z",
          },
        ],
      },
    ],
  });
  render(<ReviewQueuePage />);
  expect(await screen.findByText(/tomorrow/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the frontend tests to verify RED**

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/app/review/__tests__/page.test.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: FAIL because the client types and UI do not expect the new schedule fields.

- [ ] **Step 3: Extend the frontend schedule contracts**

```typescript
export type ReviewQueueItem = {
  ...
  due_review_date: string | null;
  min_due_at_utc: string | null;
};
```

- [ ] **Step 4: Move due-label formatting to server-backed fields**

```typescript
export function formatReviewDueLabel(item: ReviewQueueItem): string {
  if (!item.due_review_date || !item.min_due_at_utc) {
    return "Not scheduled";
  }
  return formatRelativeDueDate(item.min_due_at_utc);
}
```

- [ ] **Step 5: Run the focused frontend tests again**

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/app/review/__tests__/page.test.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/knowledge-map-client.ts frontend/src/components/review-queue/review-queue-utils.ts frontend/src/components/review-queue/review-queue-shared.tsx frontend/src/app/review/queue/page.tsx frontend/src/app/review/queue/[bucket]/page.tsx frontend/src/app/review/__tests__/page.test.tsx frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx
git commit -m "feat: render review schedule from timezone-safe due fields"
```

**Acceptance Criteria:**
- Queue/detail pages render from `due_review_date` and `min_due_at_utc`.
- Frontend does not recompute official schedule from raw elapsed hours.
- Server remains the source of truth for timezone-aware due state.

---

## Task 7: Add E2E Coverage For Alignment, Travel, Sticky Due, And Retry Separation

**Files:**
- Modify: `e2e/tests/helpers/review-scenario-fixture.ts`
- Modify: `e2e/tests/full/user-review-queue-srs.full.spec.ts`
- Modify: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`

- [ ] **Step 1: Write failing E2E scenarios**

```typescript
test("same-day reviews align to one release instant", async ({ page }) => {
  await seedAlignedReviewScenario({
    timezone: "Australia/Melbourne",
    reviewedAtUtc: [
      "2026-04-10T00:00:00Z",
      "2026-04-10T05:00:00Z",
      "2026-04-10T12:30:00Z",
    ],
    bucket: "3d",
  });
  await page.goto("/review/queue");
  await expect(page.getByText(/in 3 days|apr 13/i)).toBeVisible();
});


test("already due remains due after timezone auto-update", async ({ page }) => {
  await seedDueReviewScenario({ timezone: "Australia/Melbourne", due: true });
  await page.goto("/review/queue");
  await expect(page.getByText(/due now/i)).toBeVisible();
  await updateStoredTimezone(page, "America/Los_Angeles");
  await page.reload();
  await expect(page.getByText(/due now/i)).toBeVisible();
});
```

- [ ] **Step 2: Run the E2E targets to verify RED**

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts tests/smoke/user-review-submit.smoke.spec.ts --project=chromium`

Expected: FAIL because fixtures and UI assertions do not cover the new schedule model yet.

- [ ] **Step 3: Extend the fixtures for timezone-aware seeds**

```typescript
await seedCustomReviewQueue({
  userId,
  timezone: "Australia/Melbourne",
  items: [
    {
      srsBucket: "3d",
      dueReviewDate: "2026-04-13",
      minDueAtUtc: "2026-04-12T18:00:00Z",
    },
  ],
});
```

- [ ] **Step 4: Implement the browser assertions for travel, sticky due, and retry separation**

```typescript
await expect(page.getByText(/due now/i)).toBeVisible();
await expect(page.getByText(/tomorrow/i)).toBeVisible();
await expect(page.getByText(/same-session retry/i)).not.toBeVisible();
```

- [ ] **Step 5: Run the E2E targets again**

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts tests/smoke/user-review-submit.smoke.spec.ts --project=chromium`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add e2e/tests/helpers/review-scenario-fixture.ts e2e/tests/full/user-review-queue-srs.full.spec.ts e2e/tests/smoke/user-review-submit.smoke.spec.ts
git commit -m "test: cover timezone-safe review scheduling end to end"
```

**Acceptance Criteria:**
- E2E proves same-day alignment.
- E2E proves no early unlock on timezone change.
- E2E proves sticky due behavior.
- E2E proves same-session retry does not mutate official due scheduling.

---

## Task 8: Remove Active Legacy Raw-Hour Scheduling Paths And Final Verification

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/services/review_submission.py`
- Modify: `frontend/src/components/review-queue/review-queue-utils.ts`
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Write the final failing regression tests for removed legacy behavior**

```python
async def test_official_schedule_no_longer_depends_on_next_due_at_elapsed_hours(review_service, review_state):
    review_state.next_due_at = datetime(2026, 4, 10, 23, 0, tzinfo=timezone.utc)
    review_state.due_review_date = date(2026, 4, 11)
    review_state.min_due_at_utc = datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)
    assert review_service._resolve_official_due_at(review_state) == review_state.min_due_at_utc
```

- [ ] **Step 2: Run the focused regression tests to verify RED**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_service.py -q -k "no_longer_depends_on_next_due_at_elapsed_hours"`

Expected: FAIL if old helper paths still drive due behavior.

- [ ] **Step 3: Remove active legacy branches**

```python
# Delete or stop using:
# - raw timedelta(day) official due calculations
# - `next_due_at is None` means due-now compatibility behavior
# - official queue filters keyed only off `next_due_at <= now`
```

- [ ] **Step 4: Run the full changed-scope verification**

Run: `PYTHONPATH=backend /tmp/words-v2-test-venv/bin/pytest backend/tests/test_review_schedule.py backend/tests/test_review_service.py backend/tests/test_review_api.py backend/tests/test_user_preferences_api.py -q`

Expected: PASS.

Run: `npm --prefix frontend test -- --runInBand --runTestsByPath frontend/src/lib/__tests__/user-preferences-client.test.ts frontend/src/lib/__tests__/knowledge-map-client.test.ts frontend/src/app/review/__tests__/page.test.tsx frontend/src/app/review/queue/__tests__/page.test.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

Run: `E2E_API_URL=http://127.0.0.1:8000/api E2E_BASE_URL=http://127.0.0.1:3000 PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 E2E_DB_PASSWORD=devpassword pnpm --dir e2e test -- tests/full/user-review-queue-srs.full.spec.ts tests/smoke/user-review-submit.smoke.spec.ts --project=chromium`

Expected: PASS.

Run: `git diff --check`

Expected: PASS.

- [ ] **Step 5: Update project status**

```markdown
| 2026-04-06 | Completed timezone-safe review-day alignment for V1 review scheduling. Official due timing now persists `due_review_date` and `min_due_at_utc`, uses an authoritative IANA timezone per user, aligns same-day cards to a 04:00 local release hour, prevents early unlock during timezone changes, keeps already-due cards sticky until review, and preserves same-session retry as a separate path. | Codex | <verification commands/results> |
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/review.py backend/app/services/review_submission.py frontend/src/components/review-queue/review-queue-utils.ts docs/status/project-status.md
git commit -m "refactor: remove legacy raw-hour review scheduling"
```

**Acceptance Criteria:**
- Official due behavior no longer depends on the legacy raw-hour model.
- The active runtime is driven by `due_review_date` and `min_due_at_utc`.
- Verification covers backend, frontend, and E2E.
- Project status is updated with evidence.

---

## Spec Coverage Check

- Same-day alignment: covered by Task 1 unit tests and Task 7 E2E.
- Review-day-based official scheduling: covered by Task 3.
- Fixed local release hour: covered by Task 1 and Task 3.
- Authoritative IANA timezone: covered by Task 2 and Task 5.
- Travel east/west constraints: covered by Task 4 and Task 7.
- Sticky due: covered by Task 1, Task 4, and Task 7.
- Manual override alignment: covered by Task 3 and Task 7.
- Same-session retry separation: covered by Task 3 and Task 7.
- DST correctness: covered by Task 1 and Task 7.
- Migration/backfill: covered by Task 2.
- Legacy scheduling removal: covered by Task 8.

## Placeholder Scan

No task in this plan relies on `TODO`, `TBD`, or implicit “handle appropriately” language. Each stage names exact files, commands, and the concrete behavior to validate.

## Type And Contract Consistency Check

- Backend scheduling source of truth names stay consistent:
  - `due_review_date`
  - `min_due_at_utc`
  - `timezone`
- Frontend schedule rendering uses the same field names.
- `next_due_at` remains temporary compatibility output only during rollout and is removed from active official logic in Task 8.

