# Review Entry State Cutover Design

## Context

The learner review stack currently mixes two state models:

- legacy queue/session models backed by `ReviewCard` and related history
- entry-scoped review models backed by `EntryReviewState` and `EntryReviewEvent`

The current `Learn now` path on learner detail pages starts a session through `/review?entry_type=...&entry_id=...`, calls `POST /api/reviews/entry/{entry_type}/{entry_id}/learning/start`, renders prompts using `EntryReviewState` identifiers, and then submits through `/api/reviews/queue/{item_id}/submit`.

Manual testing shows that this flow can render a prompt and then fail on answer or continue with:

- `Queue item <id> not found`

This blocks further review and SRS debugging.

## Decision

For learner review flows, `EntryReviewState` becomes the only review state model. Legacy queue compatibility will be removed from the active learner review path. Backward compatibility is not required for this repository state.

## Scope

This slice covers:

- fixing the broken `Learn now -> prompt -> submit -> continue` flow
- removing legacy queue compatibility branches from learner review service and API code
- ensuring `learning/start` durably persists returned review state ids before the next request
- adding regression coverage for the real browser path and backend path

This slice does not yet redesign the full learning UX. It only fixes the blocker and simplifies the model so the next session can safely redesign the user-facing flow.

## Architecture

### Single Review State

`EntryReviewState` is the canonical learner review row for both:

- freshly started learning entries
- due review items

`EntryReviewEvent` remains the canonical learner review history ledger.

### Learning Start

`POST /api/reviews/entry/{entry_type}/{entry_id}/learning/start` must:

1. load the word or phrase entry
2. create or reuse target `EntryReviewState` rows for each active meaning or sense
3. durably persist those rows before returning
4. return prompts, detail payload, schedule options, and the persisted state ids

### Queue Read and Submit

`GET /api/reviews/queue/due`, `GET /api/reviews/queue/{item_id}`, and `POST /api/reviews/queue/{item_id}/submit` must resolve only through `EntryReviewState` for learner review.

No fallback to legacy `ReviewCard` rows should remain in the active learner review path.

## Error Handling

- If an entry does not exist, return `404`.
- If an entry has no meanings or senses, return `404` with a clear message.
- If a queue item id does not resolve to an `EntryReviewState` for the current user, return `404`.
- The system must not return ids from `learning/start` that cannot be resolved immediately by the next request.

## Testing

### Backend

Add regression coverage for:

- `learning/start` returns persisted `EntryReviewState` ids
- submit against a returned id succeeds
- schedule override and reveal continuation work against the same id
- legacy learner queue fallback branches are removed or no longer reachable

### E2E

Add a real browser regression test for:

1. open learner word detail
2. click `Learn now`
3. answer the first prompt or choose `Show meaning`
4. continue
5. confirm no `Queue item ... not found` runtime error appears

## Risks

- Removing legacy compatibility may break older tests that still assert `ReviewCard` behavior.
- Existing mocked frontend tests may need to be rewritten to assert the single-model behavior.
- Due review and learning-start flows currently share route names; cleanup must preserve the existing public API shape where practical for this slice.
