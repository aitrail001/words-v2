# Learner Voice Playback and Audio Review Design

## Goal

Add real learner-facing audio playback to the user frontend now that word and phrase audio assets exist, and use that same audio foundation to support voice-based review prompts. The result should be a consistent playback experience on learner detail pages, quick playback on learner tiles, and an audio review mode that uses deterministic 4-choice distractors instead of random global options.

## Scope

This design covers:

- learner word and phrase detail playback
- learner accent preference switching for quick playback
- learner tile playback controls
- review audio prompt playback and replay
- review distractor selection from same-day due entries with adjacent-frequency fallback
- relearn handoff from review into the full learner detail page

This design does not cover:

- speech capture or spoken-answer grading
- new TTS generation pipelines
- admin voice tooling
- changing the stored backend accent enum beyond the existing `us | uk | au`

## Current State

The repo already has most of the underlying pieces, but they are not connected into the learner experience.

- Learner entry detail pages are both routed through `frontend/src/components/knowledge-entry-detail-page.tsx`.
- User preferences already persist `accent_preference` in `backend/app/api/user_preferences.py` and `frontend/src/lib/user-preferences-client.ts`.
- Word detail APIs already expose `voice_assets` in `backend/app/api/words.py`.
- Review already defines `audio_to_definition` in `backend/app/services/review.py`.
- The current learner review UI renders only a dummy `Play audio` button in `frontend/src/app/review/page.tsx`.
- Review distractors are currently built from global random queries such as `order_by(func.random())`, which conflicts with the requested same-day review rule.
- Relearn currently stays inside the reduced review card state instead of opening the learner’s full entry detail view.

## Requirements

### Learner playback

1. Word detail and phrase detail pages must expose play buttons for:
   - the main word or phrase audio
   - each definition audio
   - each example audio
2. Learner tiles/cards must expose a compact play affordance for the main entry audio.
3. Learner tiles/cards must expose a compact accent switch for `US` and `UK`.
4. The accent choice must persist through the existing user preference store.
5. If an existing user still has `AU` as the stored preference, the system must remain compatible but the quick switch should only surface `US` and `UK`.

### Review behavior

1. Add a real `audio_to_definition` review mode with:
   - inline play button
   - replay button
   - exactly four answer choices labeled `A-D`
2. All MCQ review methods must build their distractors from:
   - entries due on the same day for the same user first
   - adjacent-frequency entries when the same-day pool is insufficient
3. Wrong answer, lookup, or relearn should expose the full learner detail experience rather than keeping the learner only inside a stripped relearn card.
4. The learner must still be able to continue the review flow after using the detail view.

## Design Overview

The implementation should create one shared learner voice layer and reuse it across:

- the learner detail page
- learner tiles/cards
- learner review cards

The backend should provide a learner-safe voice asset view with accent-aware selection hints. The frontend should use a single authenticated audio playback helper so protected audio URLs behave consistently everywhere.

The review service should stop using global random distractors and instead build deterministic MCQ choices from a user-specific candidate pool derived from same-day due entries and browse-rank neighbors.

## Approach Options

### Option 1: Shared learner audio foundation first

Build one playback/data-selection layer used by detail, tiles, and review.

Pros:

- one contract
- one playback implementation
- review and detail stay consistent

Cons:

- touches multiple surfaces in the same slice

### Option 2: Detail-only first, review later

Pros:

- faster visible progress

Cons:

- duplicates audio handling later
- does not satisfy the requested review outcome

### Option 3: Review-first

Pros:

- targets study behavior first

Cons:

- conflicts with requested scope priority when tradeoffs appear
- still requires shared playback shortly after

### Recommendation

Use Option 1. It is the smallest correct long-term shape and aligns with the request to prefer detail-page playback UX if scope pressure appears.

## Backend Design

### Learner entry voice contract

The learner detail APIs should expose enough structured voice information for the frontend to render:

- entry-level audio
- definition-level audio
- example-level audio

The existing `voice_assets` response from `backend/app/api/words.py` is asset-oriented and not optimized for the learner UI. The learner APIs should return a normalized voice view grouped by content target and locale so the frontend can resolve:

- preferred `US` asset
- preferred `UK` asset
- fallback asset if the selected locale is absent

This can be implemented either by:

- extending learner knowledge-map detail responses with grouped voice fields, or
- having learner detail pages fetch the word/phrase detail voice data from dedicated learner endpoints

Recommendation:

- extend learner-facing entry detail responses so the shared learner detail page can remain the single source of truth
- keep the payload grouped by semantic target instead of raw asset rows

### Accent behavior

Accent selection rules:

1. Surface only `US` and `UK` in quick playback controls.
2. Persist the selected value through the existing user-preferences endpoint.
3. If stored preference is `AU`:
   - do not break existing settings/backend behavior
   - use the best available audio fallback for playback
   - let the next explicit quick-toggle action switch the stored value into `US` or `UK`

### Playback URL behavior

Playback URLs remain protected API URLs, not direct public object links from the frontend’s perspective.

The frontend playback helper should:

1. request the asset with auth
2. create an object URL from the blob
3. reuse and revoke object URLs correctly

This avoids repeating the auth-protected `<audio src>` problem and keeps playback behavior consistent with the admin-side fix already used elsewhere in the repo.

### Review distractor sourcing

For MCQ review prompts, candidate generation should change from random global distractors to a deterministic user-local pool.

Candidate selection algorithm:

1. Build the first pool from entries due on the same day for the current user.
2. Exclude the target entry itself.
3. Filter by prompt needs:
   - entry-text distractors for definition-to-entry and related entry-choice prompts
   - definition distractors for entry-to-definition and audio-to-definition
4. If the same-day pool is too small, expand using adjacent browse-rank neighbors around the target entry.
5. Rank neighbors by absolute browse-rank distance from the target.
6. Fill to four total options including the correct answer.

This rule applies across all MCQ review methods, not only `audio_to_definition`.

### Relearn handoff

The review API does not need to redirect directly. Instead, review responses should contain enough entry identity for the frontend to:

- open the canonical learner detail route for that entry
- preserve a return token or query state so the learner can continue review afterward

The existing review payloads already include entry identity. The frontend behavior should be changed so the relearn path opens the detail page experience rather than keeping the learner on the reduced relearn card only.

## Frontend Design

### Shared audio helper

Add one learner-side audio helper/hook to:

- fetch protected audio with auth
- cache by playback URL
- manage one active `HTMLAudioElement` or equivalent per consumer
- support replay
- expose loading/error state for buttons

This helper should live in the learner frontend and be reused by:

- `KnowledgeEntryDetailPage`
- tile/range/list components that show quick playback
- `frontend/src/app/review/page.tsx`

### Detail page UX

The shared learner detail page should gain:

- a main play button in the hero for the selected accent
- a compact `US` / `UK` accent switch near pronunciation
- play buttons for each definition
- play buttons for each example

Fallback behavior:

1. selected accent
2. other surfaced accent
3. any available locale asset
4. hide or disable the control if no audio exists

### Tile/card UX

Where learner tiles already show pronunciation or act as quick-entry launchers, add:

- compact play button for main entry audio
- compact `US` / `UK` accent switch

The tile control should be lightweight and should not try to expose definition/example audio. That remains detail-page scope.

### Review UX

`audio_to_definition` cards should render:

- play button
- replay button
- question stem explaining the task
- four MCQ answers labeled `A-D`

The current dummy `Play audio` button in `frontend/src/app/review/page.tsx` should be replaced with the shared audio helper and real prompt payload data.

### Relearn UX

When the learner misses a card or chooses lookup:

- open the real learner detail route for the target entry
- preserve review context so the learner can continue the queue after viewing details

Recommended behavior:

- navigate to the entry detail page with query state indicating `return_to=review`
- show a clear “Back to review” affordance on the detail page when launched from review

This is better than embedding the full detail page inside the review screen because it reuses the canonical learner page and keeps the audio/features in one place.

## Data Contract Changes

### Learner detail payloads

The learner detail payloads should grow voice-specific fields grouped by semantic target, for example:

- entry-level grouped audio by locale
- per-definition grouped audio by locale
- per-example grouped audio by locale

The exact JSON shape can follow existing frontend conventions, but it must support:

- semantic grouping by target
- locale-aware selection
- protected playback URLs

### Review prompt payloads

Review prompt payloads should include explicit audio playback information for `audio_to_definition`:

- prompt type
- a learner-safe entry-audio object for the active prompt, keyed by locale where available
- a resolved preferred playback URL for the current review card
- audio availability state

The current `audio_state` field is insufficient by itself because the frontend cannot play real audio from it.

## Testing Strategy

### Backend

- unit tests for learner voice selection and fallback rules
- review-service tests proving same-day distractors are preferred
- review-service tests proving adjacent browse-rank fallback is used when same-day pool is too small
- review-service tests for `audio_to_definition` prompt payloads carrying real playback data

### Frontend unit tests

- detail page accent toggle persistence
- detail page main/definition/example play button rendering
- tile play button and accent switch behavior
- review audio card playback/replay rendering
- relearn flow launching the full detail page with return-to-review behavior

### E2E

- learner word detail playback smoke
- learner phrase detail playback smoke
- review audio card flow smoke
- wrong-answer relearn handoff smoke

## Risks

### Risk: voice data shape mismatch between word and phrase entries

Mitigation:

- normalize learner-facing voice fields by semantic target instead of leaking raw storage rows

### Risk: review distractor queries become expensive

Mitigation:

- keep candidate queries bounded
- use browse-rank ordered lookups instead of random global scans

### Risk: protected audio playback is flaky in the browser

Mitigation:

- use one blob-based playback helper everywhere instead of raw media URLs per component

### Risk: relearn navigation breaks queue continuity

Mitigation:

- preserve explicit return-to-review context in the learner route state/query and cover it with tests

## Acceptance Criteria

1. Learner word and phrase detail pages can play:
   - main entry audio
   - each definition audio
   - each example audio
2. Learner quick controls expose only `US` and `UK` switching and persist it.
3. `audio_to_definition` is a real playable review prompt with replay and four choices.
4. All MCQ review methods prefer same-day due distractors and use adjacent-frequency fallback when needed.
5. Wrong-answer/lookup relearn opens the canonical learner detail view and allows returning to review.
6. Unit and E2E coverage exists for the new learner voice and review behavior.
