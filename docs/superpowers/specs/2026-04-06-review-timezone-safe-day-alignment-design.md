# Timezone-Safe Review Day Alignment Design

## Goal

Make official V1 review scheduling day-based and timezone-safe so that:

- cards scheduled for the same review day unlock together at one local release time
- official scheduling is driven by review days rather than raw `+24h` math
- timezone changes never unlock cards early
- already-due cards remain due until reviewed
- same-session retry remains separate from official SRS scheduling

This design preserves the existing V1 review product behavior:

- fixed visible buckets
- success = advance exactly one bucket
- fail/check/not sure = tomorrow and back one bucket
- deterministic prompt cadence
- same manual override bucket list

The change is limited to the official scheduling layer.

## Current State

The active review redesign is already merged on `main`, but official scheduling still revolves around raw timestamps:

- `entry_review_states.next_due_at`
- `entry_review_states.recheck_due_at`
- manual override resolution in `backend/app/services/review.py`
- submit/update flows in `backend/app/services/review_submission.py`
- queue due filtering and grouping in `backend/app/services/review.py`

The current implementation does not persist:

- authoritative user timezone
- logical review-day date
- UTC minimum unlock floor separate from `next_due_at`

As a result, the system still behaves like timestamp scheduling with bucket labels layered on top.

## Non-Goals

This design does not change:

- the bucket list (`1d, 2d, 3d, 5d, 7d, 14d, 30d, 90d, 180d, Known`)
- Standard vs Deep review level behavior
- prompt family selection rules
- same-session retry timing
- multi-meaning scheduling
- the manual override choices themselves

This design also does not add per-user configurable release hours in V1. V1 uses one system-wide local release hour.

## Authoritative Scheduling Model

### User Timezone

Each user has one authoritative scheduling timezone stored as an IANA timezone string, for example:

- `Australia/Melbourne`
- `America/New_York`

The scheduling timezone must not be inferred per request from the device without updating stored state. The device may propose a change, but official due behavior must always use the stored authoritative timezone.

### Review Release Hour

V1 uses one system-wide review release hour:

- `04:00` local time

This is intentionally after midnight to avoid edge cases where cards appear immediately after a date boundary even though the learner still thinks of it as the same night.

### Effective Review Date

The effective review date is the learner’s local review day in the authoritative timezone using the `04:00` release boundary:

- if local time is before `04:00`, the effective review date is the previous calendar date
- if local time is at or after `04:00`, the effective review date is the current calendar date

Examples:

- `2026-04-10 02:30` local -> effective review date `2026-04-09`
- `2026-04-10 09:00` local -> effective review date `2026-04-10`

### Persisted Review State Fields

Official scheduling state for each review target must persist:

- `srs_bucket`
- `due_review_date`
- `min_due_at_utc`
- `last_reviewed_at`
- existing activity/suspension flags

Existing fields may remain temporarily:

- `next_due_at`
- `recheck_due_at`
- `stability`
- `difficulty`

But they stop being the source of truth for official due scheduling.

## Scheduling Rules

### Bucket-to-Day Mapping

Bucket progression remains unchanged:

- `1d` -> `+1 review day`
- `2d` -> `+2 review days`
- `3d` -> `+3 review days`
- `5d` -> `+5 review days`
- `7d` -> `+7 review days`
- `14d` -> `+14 review days`
- `30d` -> `+30 review days`
- `90d` -> `+90 review days`
- `180d` -> `+180 review days`
- `Known` -> removed from normal queue

### Computing Next Official Schedule

When a review result moves an item into a new bucket:

1. determine the user’s current effective review date
2. compute `due_review_date = effective_review_date + bucket_days`
3. compute local release instant = `due_review_date at 04:00` in the authoritative timezone
4. convert that instant to UTC and store it in `min_due_at_utc`

The next official due schedule must not be derived from:

- `reviewed_at + 24h`
- `reviewed_at + N * 24h`
- previous `next_due_at + interval`

It must always be derived from the current effective review date.

### Manual Override

Manual override remains success-only and keeps the same visible bucket list.

If the learner chooses a manual override bucket:

1. keep the normal success semantics for the review result
2. replace the recommended next bucket with the chosen bucket
3. recompute `due_review_date` from the current effective review date
4. recompute `min_due_at_utc` from the chosen bucket and authoritative timezone

Manual override must not produce staggered timestamps based on the exact submission time.

### Same-Session Retry

Same-session retry remains separate from official scheduling.

On failure:

- official bucket logic stays V1: back one bucket, floor at `1d`
- official next review becomes tomorrow in the new scheduling model
- any same-session retry remains session-only reinforcement

No second hidden official due timestamp is created.

## Due Determination

### Dual Due Check

A review target becomes officially due only when both are true:

1. current effective review date in the authoritative timezone is on or after `due_review_date`
2. current UTC time is on or after `min_due_at_utc`

This dual check serves two different purposes:

- `due_review_date` aligns cards by local review day
- `min_due_at_utc` prevents early unlock after timezone changes

### Sticky Due Rule

Once a target becomes due, it must remain due until reviewed.

Timezone changes, DST transitions, and recalculated local review dates must never hide a card that was already due.

Implementation rule:

- sticky due is enforced in review service logic
- no separate queue materialization table is required for V1

The service should treat a state as due if it has already crossed the due threshold under the previously authoritative schedule, even if a later timezone update would otherwise make the recomputed local-day test appear false.

## Timezone Update Policy

### Policy

V1 uses auto-update from the device.

When the client detects a device timezone that differs from the stored authoritative timezone:

- the client sends the new timezone to the backend
- the backend stores it as the authoritative timezone for future calculations

### Constraints

Timezone change must not:

- reset buckets
- change success/fail grading
- unlock future cards before `min_due_at_utc`
- hide already-due cards

Future due rendering and future bucket scheduling use the new timezone immediately after the update.

### Travel Behavior

Travel east:

- local date may advance earlier
- cards still must not unlock before `min_due_at_utc`

Travel west:

- local clock time may move backward
- cards still become due correctly once the dual due rule passes

Already-due cards stay due in both cases.

## DST Handling

DST correctness depends on using IANA timezones for all local date and local release calculations.

Rules:

- `due_review_date` remains a logical local review date
- local release time remains `04:00` local
- UTC unlock instant may shift across DST boundaries

That shift is expected and correct. The system must not hardcode static UTC offsets.

## Data Model Changes

### `user_preferences`

Add:

- `timezone` `String(...)` storing IANA timezone

Use `UTC` as a temporary migration fallback only if a user has no stored timezone yet. The client should populate the real timezone quickly on next preferences sync or authenticated app load.

### `entry_review_states`

Add:

- `due_review_date` as a date column
- `min_due_at_utc` as timezone-aware datetime

Retain during rollout:

- `next_due_at`
- `recheck_due_at`

### Compatibility Policy

This repository is not released yet, so the goal is not indefinite backwards-compatibility with the old scheduling design.

Allowed compatibility handling:

- one migration/backfill
- temporary derived fields during rollout

Not desired:

- permanent parallel scheduling models
- ongoing product behavior driven by old timestamp logic

## Migration and Backfill

For each active review state:

1. determine the user’s authoritative timezone
2. read the current official due instant from existing stored state, preferring `next_due_at`
3. set `min_due_at_utc` to that existing due instant
4. derive `due_review_date` by converting that instant into the user timezone and applying the `04:00` review-day boundary
5. keep the existing bucket and review history intact

Migration should preserve behavior as closely as possible for existing rows while moving future scheduling to the new source of truth.

## Service Architecture

Introduce one focused backend scheduling module responsible for:

- parsing/normalizing timezone-aware instants
- computing effective review date
- converting bucket to review-day offset
- computing `due_review_date`
- computing `min_due_at_utc`
- evaluating due-ness with sticky-due behavior
- deriving compatibility `next_due_at` values for existing consumers during rollout

Existing service layers should call this module rather than duplicating schedule math:

- `backend/app/services/review.py`
- `backend/app/services/review_submission.py`
- any queue summary/detail builder that currently reasons directly about `next_due_at`

## API and Frontend Behavior

### API

Preferences payloads must include:

- `timezone`

Queue/detail payloads should expose:

- `due_review_date`
- `min_due_at_utc`
- rendered next-review labels derived from the new scheduling model

Existing review submit endpoints do not need a breaking contract change. Scheduling semantics change server-side.

### Frontend

The client should:

- detect device timezone using IANA format
- compare it with the stored preference
- send updates when it changes

The frontend must not silently compute due state from device timezone alone. Display should use server response derived from the authoritative stored timezone.

Queue and detail pages should render:

- due labels from the new day-based schedule
- exact timestamps where helpful
- the same official bucket metadata as today

## Testing Strategy

### Unit Tests

Add focused tests for the scheduling helper module covering:

- effective review date before and after `04:00`
- bucket-to-review-day mapping
- same-day alignment for multiple review times
- DST boundary conversion
- eastward travel not unlocking early
- westward travel still unlocking correctly
- sticky-due behavior after timezone changes

### Service Tests

Add review service and submission tests for:

- success scheduling uses effective review date, not raw elapsed hours
- fail scheduling uses tomorrow based on review day, not `+24h`
- manual override recomputes from review day
- queue due logic uses dual due check
- already-due remains due after timezone update

### API Tests

Add API tests for:

- preferences timezone update
- queue/detail payload fields for `due_review_date` and `min_due_at_utc`
- non-breaking submit/manual override behavior under the new schedule model

### Frontend Tests

Add frontend tests for:

- timezone preference propagation/update behavior
- queue/detail labels derived from server-supplied due fields
- no client-side ad hoc due-date math that bypasses authoritative timezone

### End-to-End Tests

Required E2E scenarios:

1. Same-day alignment
   - review three items on the same effective review date at different local times
   - move all to `3d`
   - verify all unlock together at the same release time

2. No raw-hour staggering
   - review items at `09:00` and `21:00`
   - move both to `1d`
   - verify both unlock together next review day

3. Travel east
   - update timezone to one with earlier local date advance
   - verify future card does not unlock before `min_due_at_utc`

4. Travel west
   - update timezone to one further west
   - verify card still becomes due correctly when both due conditions are satisfied

5. Sticky due
   - make card due
   - update timezone
   - verify card stays due until reviewed

6. Manual override consistency
   - choose `7d`
   - verify next review aligns to review day plus release time, not `7 * 24h`

7. Same-session retry separation
   - fail card
   - allow same-session reappearance later
   - verify official due fields still reflect tomorrow/back-one-bucket only

8. DST correctness
   - schedule across DST transition
   - verify logical release remains `04:00` local under the new rules

## Rollout Strategy

### Stage 1

Add scheduling helper module and unit tests.

### Stage 2

Add schema fields and migration/backfill for:

- `user_preferences.timezone`
- `entry_review_states.due_review_date`
- `entry_review_states.min_due_at_utc`

### Stage 3

Move review submission and queue due logic to the new source of truth while still writing compatibility `next_due_at`.

### Stage 4

Add frontend timezone update plumbing and queue/detail rendering changes.

### Stage 5

Expand service/API/E2E coverage for travel, sticky due, DST, and manual override alignment.

### Stage 6

Remove old raw-hour scheduling paths and dead compatibility logic once all active consumers use the new fields.

## Open Tradeoffs

### Timezone Fallback Before First Sync

Some existing users may not yet have a stored timezone when the migration lands. V1 should default them to `UTC` temporarily rather than blocking scheduling, but the client should update the stored timezone as early as possible after login.

### Sticky Due Implementation

The design intentionally keeps sticky due in service logic rather than persisting a separate “was_due” state. This keeps the data model smaller, but the implementation must be carefully centralized so multiple queue readers do not drift.

### `next_due_at` During Transition

`next_due_at` can remain as a compatibility/read-model field during rollout, but it must be derived from the new day-based schedule. It must not continue to drive official behavior.
