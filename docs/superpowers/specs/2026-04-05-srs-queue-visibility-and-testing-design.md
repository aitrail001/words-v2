# SRS Queue Visibility and Testing Design

## Context

The review and scheduling stack is now active, but the product still lacks a clear way to inspect scheduled review work over longer intervals.

That creates two problems:

1. learners cannot see how their review workload is distributed across time
2. engineering and QA cannot validate long-horizon SRS behavior without either waiting in real time or relying only on low-level tests

The app already has a home review card, detail-page next-review controls, and review/debug tooling. What is missing is a product-facing queue view that represents scheduled review work clearly, plus a stronger testing surface for future-due behavior.

## Goals

- Add a learner-facing review queue page that represents the active SRS queue as grouped future review work.
- Keep the learner page limited to actual queue-backed review items only.
- Add an admin/debug queue page that exposes raw SRS state and supports time-travel QA.
- Make long-interval SRS behavior testable without waiting in real time.
- Expand automated coverage from smoke-only review checks to real scenario coverage across unit, API, E2E, and CI.

## Non-Goals

- No inclusion of `to_learn` items on the learner queue page.
- No inline schedule editing from the learner queue page.
- No exposure of raw internal SRS fields on the learner page.
- No requirement to prove SRS solely through browser tests.

## Decision

Build two surfaces on top of the same grouped queue data model:

- a learner-facing review queue page for normal product use
- an admin-only SRS debug page for QA and internal verification

Treat the queue pages as observability and navigation tools, not as the sole proof of scheduler correctness. Scheduler correctness remains grounded in frozen-time unit and API tests.

## Learner Queue Page

### Purpose

The learner queue page is a virtual review list that shows what is currently in the active review queue and when each item is expected to come back.

It should answer:

- what is due now
- what is scheduled soon
- what is scheduled far in the future
- which words or phrases are currently part of the learner's SRS workload

### Entry Point

- The home page review card includes a `View Review Queue` action.
- The learner queue page is a normal in-app page, not a debug route.

### Inclusion Rules

Show only actual queue-backed review items:

- include active `EntryReviewState` rows that are part of the learner's review queue
- exclude `to_learn` items
- exclude `known` items
- exclude entries that do not currently have active queue-backed review state

### Grouping Buckets

Group items by due-time buckets:

- `Overdue`
- `Due now`
- `Later today`
- `Tomorrow`
- `This week`
- `This month`
- `1-3 months`
- `3-6 months`
- `6+ months`

Bucket definitions must be deterministic and shared between backend/API tests and frontend rendering.

### Row Content

Each learner-facing row should include:

- entry text
- entry type (`word` or `phrase`)
- learner knowledge state
- next review time
- optional last reviewed time if already available in the current payload shape

It should feel similar to existing knowledge-list rows, but scoped to scheduled review work instead of discovery/triage.

### Learner Actions

Allowed actions on the learner page:

- open the detail page
- start review from that specific queued item

Disallowed actions on the learner page:

- no inline next-review editing
- no inline knowledge-state mutation unless that already exists as an established shared list action and does not create queue-state ambiguity

## Admin / Debug Queue Page

### Purpose

The admin/debug page exists for QA, internal verification, and diagnosis of SRS behavior over time.

It shares the same grouped queue shape as the learner page, but adds raw inspection fields and testing controls.

### Access

- Admin-only route.
- Not linked as a normal learner-facing navigation target.

### Extra Fields

The admin/debug page should expose queue-inspection fields such as:

- raw `next_review_at`
- last review outcome
- queue eligibility or inclusion reason
- current stored SRS state fields that drive scheduling
- prompt-family hint if useful for review QA

Only fields actually backed by the model should be shown. Do not invent derived internal values that the runtime does not truly use.

### Time Travel

The admin/debug page includes an effective-time override for QA:

- inspect the queue as of a future point in time
- use that effective time for bucket classification and due-state inspection
- do not mutate the real system clock
- do not persist this override as user data

This is a QA/debug control, not a learner-facing preference.

## SRS Representation

The grouped queue page is a valid representation of the SRS from a learner and QA perspective because it makes scheduled review work visible across time.

However, it is not the complete proof of SRS correctness.

The correct testing model is:

1. frozen-time unit tests for scheduling math and bucket boundaries
2. API/integration tests for queue inclusion, exclusion, and grouped responses
3. learner/admin browser tests for visible behavior and navigation

## API / Data Contract Implications

### Shared Queue Projection

Add or extend a backend queue projection that can support both pages with:

- grouped review items by due bucket
- queue counts per bucket
- row-level metadata needed for learner navigation
- optional debug-only metadata for admin inspection

Implementation may use:

- one endpoint with role-sensitive fields, or
- separate learner and admin endpoints backed by the same service

The chosen contract should preserve a single bucketing implementation so frontend and backend do not drift.

### Queue Item Start

Starting review from a specific queue item should remain deterministic:

- learner queue page can open review directly on that item
- admin/debug page can do the same when useful for QA

The current `/review?queue_item_id=...` behavior is a suitable basis if it remains consistent with the active session model.

### Effective Time Override

The debug-time override must be explicit in the API contract:

- request-level override only
- no hidden process-global state
- easy to freeze and assert in tests

## Testing Strategy

### Unit Tests

Add or expand frozen-time unit coverage for:

- scheduler interval progression after repeated successes
- scheduler regression after failure
- bucket classification at exact boundaries
- long-horizon intervals such as multi-month scheduling

These tests are the primary proof that "6 months later" behavior works without waiting 6 months.

### API / Integration Tests

Add grouped queue API coverage for:

- correct bucket assignment with fixed `now`
- `known` items excluded
- `to_learn` items excluded
- queue-backed `learning` items included
- items move between buckets under effective-time override
- debug metadata appears only on the admin/debug contract if contracts are split

### E2E Scenario Tests

Replace smoke-only confidence with broader real scenarios. Cover:

- learner queue page renders grouped buckets
- learner can open detail from the queue page
- learner can start review from a specific queued item
- successful review pushes an item into a farther bucket
- failed review reschedules according to the failure path and the item lands in the expected nearer bucket
- marking an item `known` removes it from the queue page
- `to_learn` items do not appear
- admin/debug page time travel moves future items into due buckets visibly

These should be real scenario tests with seeded deterministic data, not only smoke assertions.

### CI

CI should expose SRS coverage explicitly:

- required stable review/SRS lane stays in place
- broader review/SRS scenario suite runs automatically as part of CI
- the broader suite should validate queue grouping, navigation, and time-travel behavior instead of only smoke reachability

The goal is to catch product regressions from real scenario feedback, not merely confirm that pages load.

## UX Constraints

- The learner queue page must stay product-facing and simple.
- Debug-only concepts such as raw timestamps, SRS internals, and time override stay off the learner page.
- The learner page should feel like a virtual word list for review work, not like an engineering console.

## Risks

- Bucket boundaries can drift if frontend and backend classify time independently.
- Time-travel debugging can create confusion if it leaks into normal user state.
- Scenario-heavy E2E can become flaky if it depends on mutable live timestamps instead of deterministic seeded data.
- The queue page can become noisy if it tries to mix discovery states (`to_learn`) with active review scheduling.

## Acceptance Criteria

- A learner-facing review queue page exists and is reachable from the home review card.
- The learner queue page shows only actual queue-backed review items.
- Items are grouped into deterministic due-time buckets.
- The learner page allows opening detail and starting review from a specific queue item.
- An admin-only SRS debug page exists with raw queue/SRS inspection fields.
- The admin/debug page supports effective-time override for QA without mutating real system time.
- Frozen-time unit and API tests cover long-horizon scheduler behavior and bucket boundaries.
- Real scenario E2E tests cover grouped queue rendering, state transitions, and admin time-travel behavior.
- CI runs explicit SRS/review coverage beyond smoke-only validation.
