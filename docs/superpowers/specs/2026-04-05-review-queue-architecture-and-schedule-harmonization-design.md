# Review Queue Architecture and Schedule Harmonization Design

## Context

The first SRS visibility slice added `/review/queue` and `/admin/review-queue`, but the product still has three structural problems:

1. the learner queue and admin queue are parallel pages instead of one shared queue system
2. the learner queue is a flat grouped page instead of a summary surface with drill-in bucket views
3. the word or phrase detail page can show a `Next Review` label that disagrees with the queue because the detail page currently derives its default schedule label from rounded SRS stability while the queue uses the real scheduled timestamp

This is already visible to learners. A bucket like `Tomorrow` can contain an item whose detail page says `In 3 days`, which makes the queue feel unreliable even when the underlying SRS state is internally consistent.

The review queue is now a real product surface, not a temporary debug aid. It needs a proper shared architecture.

## Goals

- Replace the current flat learner queue page with a summary-first review queue experience.
- Add learner bucket drill-in pages with full item lists, vertical scrolling, and explicit sort/order controls.
- Rebuild learner and admin queue pages on top of one shared queue presentation model instead of separate ad hoc pages.
- Make the real scheduled due time the learner-facing source of truth everywhere.
- Seed admin review data so `admin@admin.com` can verify the admin queue and SRS debug page manually.
- Expand automated coverage from smoke-style queue checks to real scenario coverage, including long-horizon SRS advancement.

## Non-Goals

- No removal of the current adaptive SRS algorithm in this slice.
- No full redesign of the persistent learner bottom navigation beyond the requested queue label or target change.
- No inline review scheduling edits from queue list pages.
- No exposure of admin-only debug fields on learner-facing routes.
- No attempt to reduce the full SRS algorithm to a fixed 1/3/7/14-day ladder internally.

## Decision

Implement a shared review-queue architecture with two levels of learner navigation and an admin-only debug layer:

- learner queue summary page
- learner bucket detail pages
- admin queue summary page
- admin bucket detail pages

All four routes will be backed by one queue service contract family and one shared frontend queue module.

The learner-visible schedule source of truth becomes the actual scheduled timestamp (`next_review_at`), not the coarse schedule override bucket derived from rounded stability.

## Product Shape

### Learner Summary Page

Route:

- `/review/queue`

Purpose:

- show the learner how review work is distributed over time
- act as a list of queue buckets rather than a full item dump

Each bucket card shows:

- bucket name
- item count
- a short summary such as the earliest due time and one or two preview entries
- an `Open` action to drill into the bucket
- `Start Review` only for due buckets when that makes sense at the bucket level

The summary page should feel like a list of queue lists, not the full queue itself.

### Learner Bucket Detail Page

Route:

- `/review/queue/[bucket]`

Purpose:

- show the full list of items inside one queue bucket
- support normal browsing of that bucket with vertical scrolling

Content:

- bucket heading and count
- list rows for every item in that bucket
- next review timestamp
- last reviewed timestamp when available
- entry type and learner status

Controls:

- sort selector
- order selector
- `Open detail`
- `Start review` for due items only

Sorting should be deterministic and backed by the server contract so E2E can verify it cleanly.

### Admin Summary Page

Route:

- `/admin/review-queue`

Purpose:

- mirror the learner summary page structure
- add internal SRS inspection controls

This page should use the same bucket summary model as the learner page, not a separate ad hoc layout.

It additionally includes:

- effective-time override
- generated-at metadata
- access to bucket drill-in pages

### Admin Bucket Detail Page

Route:

- `/admin/review-queue/[bucket]`

Purpose:

- expose the full contents of one bucket plus raw SRS/debug state

In addition to learner-visible row data, admin rows can show:

- raw `next_review_at`
- raw `next_due_at`
- `recheck_due_at`
- `last_outcome`
- relearning state
- prompt-family hint when useful
- any directly stored scheduling fields the runtime truly uses

Admin detail pages also inherit the request-scoped `effective_now` override.

## Shared Queue Architecture

### Frontend

Create a dedicated shared review queue module in the frontend for:

- bucket labels
- bucket ordering
- common queue row rendering
- bucket summary card rendering
- bucket detail list rendering
- shared timestamp formatting rules
- learner-safe vs admin-debug field separation

The learner and admin pages should compose these shared queue components rather than reimplementing similar markup twice.

### Backend

Expose queue data through one shared projection family:

- summary projection by bucket
- bucket detail projection with sorting and ordering
- learner contract
- admin contract with extra debug fields

Implementation may use separate learner/admin endpoints, but both must call the same internal queue projection code so bucket logic, sorting, and counts cannot drift.

## Source of Truth for Next Review

### Current Problem

Today:

- queue pages show the actual scheduled timestamp from `next_review_at`
- detail pages default the `Next Review` dropdown from rounded `stability`

That creates visible disagreement.

### Decision

For learner-facing display, the current schedule is always the actual scheduled timestamp.

The detail page must therefore show:

- the actual next review date and time
- a schedule override dropdown as a separate control

The dropdown is not the current truth. It is only a manual override affordance.

### Required Detail-Page Behavior

The detail page review panel should distinguish clearly between:

- `Scheduled for <exact date/time>`
- `Change next review`

If the current actual due time is April 6, 2026 at 13:52, the detail page must not claim `Tomorrow` or `In 3 days` unless the actual scheduled timestamp truly matches that label.

Manual override labels may stay coarse (`Tomorrow`, `In 3 days`, `In a week`, and so on), but they should be presented explicitly as override choices, not as the current schedule label.

## Harmonizing Adaptive SRS with Manual Override

The current algorithm is intentionally flexible and may produce arbitrary day counts or timestamps. That should remain true internally.

To avoid learner confusion:

- learner-facing queue pages show exact schedule timestamps
- learner-facing detail pages show the exact current timestamp first
- manual override choices remain bucketed and human-readable
- copy must make clear that the dropdown changes the schedule rather than restating it

The learner should understand:

- the system scheduled this item for an exact time
- they may optionally change that schedule using a simpler bucketed override

This keeps the adaptive SRS while making the UI coherent.

## Confidence Check Scheduling

`confidence_check` remains a real prompt family with its own scheduler influence.

This slice does not add a second separate difficulty system just for confidence prompts. Instead:

- confidence-check stays part of the existing prompt-type-aware scheduler
- its prompt-type weighting remains explicitly test-covered
- admin debug pages should show enough row/event context for QA to verify confidence-check outcomes in the queue history and resulting intervals

## Admin Manual Seed Data

Manual queue seeding must support both:

- `user@user.com`
- `admin@admin.com`

The seeded admin queue should use the same real snapshot-backed word and phrase data as the learner queue and should be deterministic enough for manual QA of:

- learner summary queue
- learner bucket drill-in pages
- admin summary queue
- admin bucket drill-in pages
- effective-time override
- detail-page schedule consistency

The admin queue seed path should not require special one-off records unrelated to the standard review scenario fixtures.

## Navigation

The top navigation label currently says `Review` and points to `/review`.

For this slice it should become:

- label: `View Review Queue`
- target: `/review/queue`

This makes navigation match the product’s new review queue entry point.

The actual act of doing due review still happens from:

- `Start Review` on the home card
- queue summary or bucket detail `Start review` actions

## Testing Strategy

### Unit Tests

Add or extend unit coverage for:

- bucket summary projection
- bucket detail sorting and ordering
- bucket boundary classification
- detail-page schedule payload derived from actual due time instead of rounded stability
- confidence-check prompt-family scheduling factor
- long-horizon advancement from repeated successful reviews out toward multi-month intervals

Long-horizon tests should not wait in real time. They should freeze time and submit repeated review outcomes.

### API Tests

Add API coverage for:

- learner queue summary response
- learner bucket detail response
- admin queue summary response
- admin bucket detail response
- sorting and ordering semantics
- admin-only debug fields
- `effective_now` behavior on both admin summary and admin bucket detail routes
- exact-timestamp schedule payload consistency between queue and detail responses

### E2E Tests

Add real scenario E2E coverage for:

- learner summary page renders bucket cards with counts and `Open`
- learner bucket detail page lists all items in the selected bucket
- learner can sort and reorder bucket detail items
- learner can start review from a bucket detail page item
- successful review moves an item into a farther bucket
- failed review moves an item into a nearer or relearning-related bucket as expected
- marking an item `Already Knew` removes it from queue surfaces
- admin summary page loads seeded admin data
- admin bucket detail page shows extra debug fields
- admin effective-time override pulls a future item into a due bucket
- repeated correct reviews can be driven far enough that an item lands in a long-horizon bucket like `3-6 months` or `6+ months`

### CI

The required review/SRS CI lane should continue to run real browser scenarios, not only smoke tests.

At minimum, CI should cover:

- learner queue summary and drill-in
- admin queue inspection
- schedule consistency regression
- long-horizon advancement scenario

## Risks

### Scope Risk

This is broader than a label-only or page-only patch because it intentionally replaces the queue architecture. The risk is acceptable because the current split model is already causing product confusion.

### UX Risk

If the detail page continues to blur exact schedule versus override choice, the queue will still feel inconsistent. The copy and component structure need to make this distinction obvious.

### Test Fragility Risk

Queue tests can become brittle if time is not controlled carefully. Unit and API tests should freeze time wherever possible, and E2E fixtures should seed deterministic due dates.

## Acceptance Criteria

- Learner queue is a bucket summary page, not a flat full-queue dump.
- Each learner bucket opens a dedicated bucket detail page with sort and order controls.
- Admin queue follows the same summary/detail architecture with extra debug fields.
- `admin@admin.com` has deterministic review seed data for manual QA.
- The detail page no longer shows a current next-review label that disagrees with the actual queue timestamp.
- Manual override remains available but is clearly presented as an override, not the source of truth.
- Confidence-check remains a prompt-family-aware scheduling input and is covered by tests.
- E2E and CI include real long-horizon SRS progression scenarios, not only smoke checks.
