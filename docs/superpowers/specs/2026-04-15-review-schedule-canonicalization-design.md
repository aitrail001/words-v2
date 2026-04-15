# Review Schedule Canonicalization Design

**Date:** 2026-04-15
**Status:** Proposed
**Owner:** Codex + user

## Goal

Make the official review-day model the only normal scheduling model for review items, remove legacy schedule paths and schema that create conflicting user-facing timing, preserve `recheck_due_at` as the only sanctioned short-term retry mechanism, and align learner/admin rendering plus test gates around one canonical contract.

## Problem

The current review experience exposes multiple scheduling models at once:

- the official review-day model based on `due_review_date` and `min_due_at_utc`
- raw exact timestamps such as `next_review_at` and `next_due_at`
- a short-term retry path using `recheck_due_at`
- frontend components that recompute due labels independently from partially overlapping fields

This creates inconsistent UX such as:

- a queue group labeled `Tomorrow` while an item card says `Due now`
- learner detail pages showing exact times like `00:21` or `15:35` that conflict with the product rule that reviews release at `4:00 AM` local time
- tests that lock in exact legacy timestamp rendering rather than the intended user model

The user explicitly wants to remove legacy code and schema that support the old timestamp-driven model because keeping both models active is confusing.

## Desired Outcome

### Learner-facing behavior

- Normal review scheduling is expressed through one canonical learner-facing model.
- Learner queues, queue detail, word detail, phrase detail, and any other learner schedule UI use the same presentation contract.
- Learners do not see raw legacy exact timestamps as the primary schedule message.
- The official release rule remains `4:00 AM` in the learner's local timezone.

### Admin behavior

- Admin views use the same canonical primary schedule message as learners.
- Admin may additionally show exact/internal timing fields for support and diagnostics.
- Diagnostic fields are visually and semantically secondary, never mixed into the main learner-facing schedule message.

### Scheduling behavior

- `due_review_date` + `min_due_at_utc` is the only normal schedule model.
- `recheck_due_at` survives as a distinct short-term retry mechanism after failed reviews.
- When a short-term retry would land too late in the local day, it rolls to the next day's canonical review release window instead of creating an awkward late-night retry timestamp.

## Canonical Contract

### Canonical persisted model

For normal review scheduling, the canonical persisted fields are:

- `due_review_date`
- `min_due_at_utc`

These fields encode:

- the learner's effective review day
- the earliest UTC instant at which the item becomes available for that review day

For short-term relearning only, the allowed exception is:

- `recheck_due_at`

`recheck_due_at` is not a legacy fallback. It is a distinct product rule for rapid retry after failure.

### Canonical learner-facing message

Every learner-facing surface should derive its primary schedule copy from a single shared formatter that consumes canonical schedule data, not whichever raw timestamp happens to be available.

Primary learner-facing schedule outputs include:

- `Due now`
- `Later today`
- `Tomorrow`
- `In N days`
- equivalent longer-range labels already supported by the review queue utilities

Whether learner surfaces also show an exact time should be governed by the canonical schedule contract, not by direct rendering of raw legacy timestamps.

### Canonical admin message

Admin receives:

- the canonical learner-facing schedule message
- explicit diagnostic fields when needed, such as canonical due instant, retry instant, and schedule source

Admin exact/internal timestamps must be labeled as diagnostics or internal schedule fields.

## Legacy Removal Policy

The following categories must be reviewed and removed where they exist only to support the old timestamp-driven schedule model:

1. Schema fields whose only purpose is normal legacy schedule fallback.
2. Backend service branches that treat legacy exact due timestamps as equivalent to canonical review-day scheduling.
3. API response fields that expose legacy schedule semantics into learner-facing contracts.
4. Frontend rendering paths that display schedule timing from raw exact timestamps instead of canonical schedule data.
5. Tests that assert legacy exact-time rendering for learner-facing UX.

This design does **not** remove `recheck_due_at`, because it is an intentional relearning mechanism.

## Recheck Policy

`recheck_due_at` remains the only sanctioned exact-time retry path.

### Purpose

- Trigger a short-term relearning retry after failed review outcomes.
- Preserve immediate reinforcement without polluting the main review-day model.

### Policy

- Keep a short same-day retry interval.
- Make the interval policy-driven rather than an accidental implementation detail.
- If the retry would land too late in the learner's local day, move it to the next day's canonical review release window.

### Product rationale

- preserves quick reinforcement after mistakes
- avoids weird late-night retry scheduling
- keeps the long-term mental model simple: normal reviews release at the canonical daily review window

The exact local "too late" cutoff should be specified during implementation, but the core behavior is fixed by this design: late retries roll to the next canonical release window.

## Systematic Review Scope

### Database and migrations

Audit:

- `backend/app/models/entry_review.py`
- existing review scheduling migrations such as `051_timezone_safe_review_sched.py`
- any earlier schema introduced for legacy exact scheduling

Determine:

- which columns remain necessary for canonical scheduling plus `recheck_due_at`
- which columns are legacy and should be deprecated, migrated away, and dropped

### Backend services

Audit:

- `backend/app/services/review.py`
- `backend/app/services/review_submission.py`
- `backend/app/services/review_schedule.py`
- any query or grouping logic that sorts, filters, or labels by raw exact due timestamps

Determine:

- all writers of `due_review_date`, `min_due_at_utc`, `next_due_at`, `next_review_at`, and `recheck_due_at`
- all code paths that prefer raw exact due timestamps over the canonical schedule
- all places where learner/admin output contracts can be made explicit rather than inferred by frontend code

### APIs and response contracts

Audit:

- `backend/app/api/reviews.py`
- `backend/app/api/knowledge_map.py`
- typed frontend client models in `frontend/src/lib/knowledge-map-client.ts`

Determine:

- which fields should stay in learner-facing contracts
- which fields should become admin-only diagnostics
- which fields should be removed entirely after legacy cutover

### Learner frontend

Audit all learner-facing schedule rendering, including:

- review queue shared components
- review queue pages
- learner word detail
- learner phrase detail
- any other surfaced "Next review" or due-label UI

Key targets already identified:

- `frontend/src/components/review-queue/review-queue-utils.ts`
- `frontend/src/components/review-queue/review-queue-shared.tsx`
- `frontend/src/components/knowledge-entry-detail-page.tsx`

Determine:

- every learner-facing place that still directly renders exact timestamps
- whether the component is using shared canonical formatting or a private rendering path

### Admin frontend

Audit:

- admin review queue routes and cards
- admin detail or diagnostic views that expose schedule data

Determine:

- which exact/internal fields are genuinely useful for operators
- how to clearly separate canonical user-facing schedule from diagnostics

## Architecture Direction

### Backend

Backend should become the source of truth for schedule meaning, not merely a transport of partially overlapping fields.

Direction:

- canonicalize schedule serialization around review-day semantics
- preserve `recheck_due_at` as a clearly separate retry concept
- remove normal legacy fallback branches
- make learner/admin API contracts explicit rather than requiring frontend recomputation of meaning from raw timestamps

### Frontend

Frontend should have one shared learner-facing schedule formatter and one explicit admin diagnostic formatter or field group.

Direction:

- learner surfaces consume canonical schedule presentation data or a single shared canonical formatter
- learner surfaces stop rendering raw exact timestamps from `next_review_at` fallback logic
- admin surfaces may display diagnostics, but only in clearly separated UI

## Testing and Gate Changes

The previous gate hardening added route-runtime coverage. This project adds semantic schedule consistency coverage.

Required coverage additions:

1. Backend unit/integration tests
- canonical scheduling is derived only from `due_review_date` + `min_due_at_utc` for normal review items
- legacy normal-schedule fallback behavior is removed
- `recheck_due_at` remains functional for failed reviews
- late-night `recheck_due_at` rolls to next-day canonical release

2. Frontend unit tests
- learner queue card and learner detail views use the same canonical schedule logic
- learner detail no longer shows raw exact timestamp as the primary next-review message for canonical review-day items
- admin views retain diagnostics without changing the primary canonical message

3. E2E / route-runtime checks
- learner queue and learner detail pages agree on the displayed next-review meaning
- admin queue page shows canonical schedule plus diagnostics
- no mixed `Tomorrow`/`Due now` contradictions for the same item under the same effective time

4. Gate wiring
- add the new tests to the shared CI grouping definitions first
- update `gate-fast`, `gate-full`, and GitHub CI in the same change
- preserve thin-workflow rule by keeping logic in repo-owned scripts

## Migration Strategy

Because the user wants legacy schema and code removed, implementation should include a cleanup migration plan rather than permanent dual-read behavior.

High-level migration phases:

1. Audit all legacy schedule fields and usages.
2. Identify fields that are still needed for canonical schedule plus `recheck_due_at`.
3. Convert code paths to canonical-only normal scheduling.
4. Update API contracts and frontend consumers.
5. Backfill or transform persisted data if any remaining rows depend on legacy fields for normal scheduling.
6. Drop obsolete schema and dead code once canonical behavior is verified by tests and gates.

The implementation may use a temporary internal transition step, but the final state should not preserve legacy normal-schedule schema "just in case."

## Risks

### Risk: hidden dependency on legacy timestamp fields

Older tests, admin diagnostics, or background code may still rely on legacy fields.

Mitigation:

- perform a repo-wide audit before deleting fields
- update tests and contracts in the same PR series

### Risk: frontend/backend contract drift during cutover

If frontend keeps recomputing schedule meaning from deprecated fields, the UX may remain inconsistent.

Mitigation:

- make backend schedule semantics explicit
- remove private learner-side rendering paths that bypass the shared contract

### Risk: recheck policy changes user learning cadence

Changing late-night retry behavior is a product change, not just a refactor.

Mitigation:

- add explicit tests around same-day and late-night retry behavior
- document the policy in code and, if needed, in an ADR

## ADR Recommendation

This project should produce an ADR once implementation direction is finalized.

Recommended ADR topic:

- canonical review-day scheduling as the sole normal review model
- `recheck_due_at` retained only for bounded short-term relearning retries
- learner/admin display split between canonical UX and explicit diagnostics

`docs/adr/` does not exist today, so ADR creation must follow the explicit approval flow defined by the ADR skill when implementation reaches that decision point.

## Out of Scope

- changing the core spaced-repetition bucket ladder itself
- redesigning the learner queue UX beyond schedule consistency
- broad unrelated refactors in knowledge map or review UI
- changing admin permissions or non-schedule admin workflows

## Implementation Readiness

This work is large enough to warrant:

- a dedicated worktree branch
- a written implementation plan
- staged execution across audit, canonicalization, migration, and gate updates

The next artifact after this design is a task-by-task implementation plan.
