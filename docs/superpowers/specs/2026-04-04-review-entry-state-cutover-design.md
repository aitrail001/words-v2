# Review Entry State Cutover Design

## Context

The learner review flow currently mixes multiple state models and multiple post-answer handoff paths:

- legacy queue/session behavior from `ReviewCard`-style runtime paths
- entry-scoped review state via `EntryReviewState`
- success/failure UI handoffs split across inline reveal cards, relearn cards, and detail-page navigation

That mix creates two concrete problems:

1. runtime instability, including the earlier `Queue item <id> not found` failure after `Learn now`
2. ambiguous behavior after answering a prompt, which makes the product harder to reason about and the browser coverage brittle

This design locks a single review-state model and a single post-answer state machine for all prompt families.

## Goals

- Make `EntryReviewState` the only learner review state model.
- Remove legacy learner-review runtime compatibility.
- Standardize every prompt family onto one post-answer contract.
- Separate review success, review failure, and guided relearn clearly.
- Prevent immediate same-session retries after a failed answer so the learning algorithm is not biased by short-term priming.
- Make the flow deterministic enough for unit, API, E2E, and CI coverage.

## Non-Goals

- No backward-compatibility layer for unpublished legacy learner-review behavior.
- No prompt-family-specific post-answer UX.
- No user schedule override on the failed / relearn path.
- No dedicated review section at the bottom of the home page.

## Decision

For learner review flows, `EntryReviewState` becomes the only active review-state model, and every prompt family uses the same state machine:

- correct answer -> normal entry detail page
- wrong answer or `Show meaning` -> guided relearn pass
- guided relearn completion -> next queue item, not the same item again

## Canonical State Machine

### Queue Entry

- The home page shows a review card only when due queue count is greater than zero.
- `Start Review` from the home page goes directly into the first due queue item.
- `/review?resume=1` resumes the next pending item in the current review session.

### Prompt State

The active prompt screen is the only place where users answer review questions.

- Keep the prompt-family-specific answer UI.
- Remove `I remember it`.
- Keep `Show meaning`.
- Show review progress as `Review x / y` inside the review shell only.

### Correct Answer Path

For every prompt family:

1. user submits a correct answer
2. app transitions to the normal detail page for that word or phrase
3. main entry audio auto-plays on page load
4. the detail page shows the existing next-review controls
5. the review result is not finalized until the user clicks `Continue review`
6. clicking `Continue review` persists the selected schedule and advances to the next queue item

This keeps the detail page as the canonical success confirmation surface instead of using inline reveal cards.

### Wrong Answer / Show Meaning Path

For every prompt family:

1. user answers incorrectly or clicks `Show meaning`
2. the review attempt is recorded as failed
3. the failed item is auto-scheduled by the algorithm with no user override
4. the app enters a guided relearn pass
5. after relearn completes, the app advances to the next queue item

The failed item is not re-asked in the same session.

## Guided Relearn Pass

The guided relearn pass mirrors `Learn now` behavior:

- step through each definition/example in order
- auto-play definition and example audio where available
- require explicit `Next` progression through all senses / meanings
- reuse the normal learning presentation rather than inventing a parallel mini-review UI

This pass is for repairing understanding, not for gathering another review-grade signal. It does not return to the same prompt afterward.

## Scheduling Rules

### Success Path

- Detail page shows the next-review dropdown.
- The user may adjust the next review timing before continuing.
- The selected option is persisted only when `Continue review` is clicked.

### Failed Path

- The algorithm chooses the failed interval automatically.
- No user override is shown in this path.
- The system should not default failed items to a manual option such as `Later today` unless the algorithm itself chooses that interval.

## Knowledge-State Rules

- `Already Knew` remains separate from next-review scheduling.
- `Already Knew` changes the entry knowledge state to `known`.
- Marking an entry as `known` keeps review history but removes it from the active due queue.
- Scheduling controls such as `Pause review` do not change knowledge state.

## Home and Resume Behavior

- The home page review card only appears when there are due items.
- The home page card shows the due count, not `x / y`.
- `x / y` is shown only inside the active review flow.
- Returning from the detail page via `Back to review` or `Continue review` should continue from the next pending queue item in the current session.

## API / Data Contract Implications

### Canonical Model

- `EntryReviewState` is the only active learner-review queue row.
- `EntryReviewEvent` remains the history ledger.
- Legacy runtime read/submit paths are removed from learner review.

### Success Submission

Backend must support:

- validating the correct answer
- deferring final persistence of the chosen next-review schedule until the success detail step is confirmed

This can be modeled as either:

- a pending success transition held in review-session state until `Continue review`, or
- an immediate provisional submission with an updateable schedule before advancement

Implementation should choose the simpler version that preserves the product contract above.

### Failed Submission

Backend must support:

- immediate failed submission
- algorithm-selected failed interval
- guided relearn metadata for the current entry
- advancing the session without re-queuing the same item into the current run

## Testing Requirements

### Backend / Unit / API

Add or update coverage for:

- `learning/start` returns persisted `EntryReviewState` ids
- correct answer does not advance until `Continue review`
- wrong answer and `Show meaning` both record failure and schedule automatically
- failed items do not reappear in the same session
- `known` items retain history but are excluded from active due review
- legacy learner-review model paths are no longer reachable

### Frontend

Add or update coverage for:

- all prompt families share the same success handoff into the normal detail page
- `Show meaning` and wrong answers both enter the guided relearn flow
- review progress renders as `Review x / y` only in the review shell
- the home review card appears only when the queue has due items

### E2E / CI

Seed deterministic queue items that cover:

- multiple-choice definition recall
- audio-to-definition
- sentence gap / fill-in
- typed recall
- phrase scenarios

For each family, cover:

- correct path -> detail page -> `Continue review` -> next item
- failed path -> guided relearn -> next item
- no same-session immediate retry after relearn

## Risks

- Some current tests likely encode old handoff assumptions and will need to be rewritten.
- The success-path persistence point must be explicit; otherwise the frontend and backend will diverge again.
- Reusing the learning pass inside review failure handling may require clearer session-state boundaries than the current implementation has.

## Acceptance Criteria

- No learner-review runtime path depends on legacy `ReviewCard`-style state.
- `Learn now` and due review both run on `EntryReviewState`.
- Any correct answer from any prompt family goes to the normal detail page.
- Any wrong answer or `Show meaning` enters guided relearn.
- Guided relearn completes and advances to the next queue item without re-asking the failed one.
- The failed item’s schedule is algorithm-selected with no user override in that path.
- The success detail page requires `Continue review` to finalize and advance.
- Automated coverage exists across backend, frontend, E2E, and CI for the above contracts.
