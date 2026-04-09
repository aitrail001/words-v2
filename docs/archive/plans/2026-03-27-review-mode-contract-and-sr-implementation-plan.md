# Review mode contract + Spaced Repetition implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a mode-based review system that supports `MODE_MCQ` and `MODE_CONFIDENCE` as first-class modes (plus optional `MODE_TYPED`), while keeping per-word/per-entry learning behavior and using spaced repetition scheduling with override controls.

**Architecture:** Build prompt-generation and review-mode routing in `backend/app/services/review.py` and `backend/app/api/reviews.py`, keep queue and history storage unchanged, and implement interactive review/fallback flow in `frontend/src/app/review/page.tsx` plus Learn Now/lookup-trigger wiring from `frontend/src/components/knowledge-entry-detail-page.tsx`.

**Tech Stack:** FastAPI, SQLAlchemy (async), PostgreSQL, React/Next.js (TypeScript), Pytest/Jest.

---

## Approved mode approach

### Approach 1 (recommended)
- Keep storage models mostly unchanged.
- Add prompt/mode metadata in API responses and submission payloads.
- Use existing SM-2 service for scheduling, plus optional client-selected interval override.
- Add fallback route for learning-start to guarantee first-learning flow can always begin.

### Why this approach
- Minimal schema risk.
- Fastest rollout with per-word behavior preserved.
- Leaves room for future strict server-side correctness checks.

### Why not server-authoritative answer checking yet
- Current prompt payload is generated at queue fetch time and not persisted for historical replay.
- We avoid cross-table migration in this slice and keep behavior stable.

---

## API contract (v1)

### Queue due item (GET `/api/reviews/queue/due`)
Add optional fields to `QueueItemResponse`:

```json
{
  "id": "uuid",
  "item_id": "uuid",
  "word_id": "uuid",
  "meaning_id": "uuid",
  "card_type": "word_to_definition",
  "review_mode": "mcq|confidence|typed",
  "review_session_id": "uuid | null",
  "prompt": {
    "mode": "mcq|confidence|typed",
    "prompt_type": "voice|definition|sentence",
    "stem": "The prompt shown to learner",
    "question": "word|definition|sentence-with-blank",
    "audio_state": "not_available",
    "options": [
      { "option_id": "A", "label": "...", "is_correct": true },
      { "option_id": "B", "label": "...", "is_correct": false },
      { "option_id": "C", "label": "...", "is_correct": false },
      { "option_id": "D", "label": "...", "is_correct": false }
    ],
    "expected_input": "...",    // only for typed mode
    "sentence_masked": "... ___ ...", // only for sentence mode
    "source_word_id": "uuid",
    "source_meaning_id": "uuid"
  },
  "session_id": "uuid | null",
  "review_count": 0,
  "correct_count": 0,
  "next_review": null
}
```

Rules:
- `review_mode: mcq` includes 4 options in `prompt.options`.
- `review_mode: confidence` does not include options; only `I remember` and `Lookup` are supported controls.
- `prompt.audio_state` for voice-mode is `not_available` until TTS integration.
- `prompt.is_correct` should only be returned to debug/admin builds; set to `false` in production review API responses, or omit entirely and rely on server-side answer evaluation in a later release.

### Submit review (POST `/api/reviews/queue/{item_id}/submit`)
Update `QueueSubmitRequest`:

```json
{
  "quality": 0,
  "time_spent_ms": 1000,
  "card_type": "word_to_definition",
  "review_mode": "mcq|confidence|typed",
  "selected_option_id": "A",
  "typed_answer": "...",
  "schedule_override": "10m|1d|3d|7d|14d|1m|3m|6m|never_for_now"
}
```

Rules:
- `quality` remains canonical for SM-2.
- `schedule_override` is optional and maps to effective next-review interval.
- `schedule_override = never_for_now` maps to long-dormant interval (default 365 days) and should never be treated as infinite.
- `selected_option_id`/`typed_answer` are optional telemetry fields until server-side answer verification is added.

### Learn-now + fallback entry start
Add endpoint:
- `POST /api/reviews/entry/{entry_type}/{entry_id}/learning/start`
- Returns:
  - `entry_type`, `entry_id`, `entry_word`, `meaning_ids`, `queue_item_ids`
  - `cards` for immediate learning stack (all meanings)
  - `requires_lookup_hint`: true

This endpoint is used for:
- `Learn Now` action on detail page.
- `Lookup` and wrong-answer fallback to route into first-learning flow.

---

## Spaced repetition override mapping

Mapping values:
- `10m` => `0.007` days
- `1d`  => `1` day
- `3d`  => `3` days
- `7d`  => `7` days
- `14d` => `14` days
- `1m`  => `30` days
- `3m`  => `90` days
- `6m`  => `180` days
- `never_for_now` => `365` days

Quality mapping in this phase:
- `I remember` => `quality=5`
- `MODE_MCQ` correct => `quality=4`
- `MODE_MCQ` wrong => `quality=1`
- `Lookup` => `quality=1` + launch fallback first-learning flow

---

## Frontend review state machine

1. `session_start`
2. `session_active` with active `card`
3. `mode_rendered` with prompt and response controls
4. `post_success` (show detail + reschedule choices)
5. `fallback_learning` (iterate through all definitions)
6. `next_card_or_complete`

Mode rendering:
- `review_mode = mcq` → show A-D choices.
- `review_mode = confidence` → show only `I remember` and `Lookup` actions.
- `review_mode = typed` (optional phase 2) → text box + submit button.
- No `Skip` action at all.

---

## Required file changes

### Task 1: Backend API contracts
**Files**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/models/review.py` (only if interval override needs persisted extension)

**What to change**
1. Add/extend Pydantic models:
   - `ReviewPromptPayload`, `ReviewChoice`, `ReviewScheduleOverride`, request/response fields.
2. Extend `QueueItemResponse` with `review_mode`, `prompt`, and optional `audio_state` metadata.
3. Extend `QueueSubmitRequest` with `review_mode`, `selected_option_id`, `typed_answer`, `schedule_override`.
4. Add endpoint `POST /reviews/entry/{entry_type}/{entry_id}/learning/start`.

### Task 2: Backend prompt + scheduling service
**Files**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/spaced_repetition.py` (optional helper for override interval conversion)

**What to change**
1. Add prompt-builder methods for each card prompt type:
   - definition-to-word
   - word-to-definition
   - sentence_blank
2. Add distractor builder:
   - same entry type + nearby entries
   - fallback to random global meanings when insufficient candidates
3. Wire prompt builder into `get_due_queue_items()`.
4. Add interval override function and apply in `submit_queue_review()`.
5. Add `entry learning start` service method to collect all meanings for word/phrase and seed missing queue items.

### Task 3: Backend tests
**Files**
- Modify: `backend/tests/test_review_api.py`
- Modify: `backend/tests/test_review_service.py`

**What to change**
1. Add API tests:
   - due payload includes `review_mode` + `prompt` and MCQ options.
   - queue submit accepts new payload fields.
   - schedule override updates next-review behavior.
   - learning-start endpoint creates/reuses queue items for all meanings.
2. Add service tests:
   - schedule override mapping behavior.
   - fallback to `definition` prompt when sentence unavailable.
   - MCQ generation returns 4 unique options.

### Task 4: Frontend types + review page flow
**Files**
- Modify: `frontend/src/app/review/page.tsx`
- Add: `frontend/src/lib/review-session-client.ts` (optional shared types + mapper)

**What to change**
1. Replace numeric rating buttons with mode-aware interaction.
2. Support two concrete modes for this release:
   - `MCQ` (A-D)
   - `Confidence` (`I remember`, `Lookup`)
3. Remove Skip support entirely.
4. Implement post-success detail reveal and scheduling buttons using override options list.
5. Implement fallback entry-learning path for wrong and `Lookup` actions.

### Task 5: Frontend Learn Now and detail page integration
**Files**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts`

**What to change**
1. Add `startLearningEntry(entry_type, entry_id)` call in client library.
2. In detail page, replace `Learn Now` action to:
   - call `startLearningEntry` endpoint,
   - navigate to `/review?mode=learning&entry_type=...&entry_id=...`.
3. Show progress or inline error state if learning start fails.

### Task 6: Frontend tests
**Files**
- Modify: `frontend/src/app/review/__tests__/page.test.tsx`
- Add: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx` (if missing)

**What to change**
1. Update review tests from numeric rating to:
   - render `review_mode=mcq` and A-D.
   - render confidence buttons for fallback/continue path.
2. Add `Learn Now` integration test for calling new start-learning client and route transition.

### Task 7: Docs + rollout notes
**Files**
- Modify: `docs/status/project-status.md`
- Add/Modify: `docs/plans/2026-03-27-review-mode-contract-and-sr-implementation-plan.md` (this file)

**What to change**
1. Mark plan status as implemented-in-progress when coding begins.
2. Add concise behavior note:
   - no Skip mode,
   - confidence mode is separate from MCQ,
   - optional modes planned.

---

## Open questions before implementation
1. Confirm whether `never_for_now` should be exactly `365 days` or a separate `no_review_until_manual` flag later.
2. Confirm if typed mode ships in this slice or phase-2.

## Delivery order
- Tasks 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7.
