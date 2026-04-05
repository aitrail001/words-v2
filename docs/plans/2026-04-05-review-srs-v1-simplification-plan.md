# Review + SRS V1 Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current adaptive, multi-meaning, partially same-day learner review runtime with a deterministic, first-meaning-only, bucket-based V1 review system that is simpler to explain, simpler to test, and compatible with the existing lexicon data model.

**Architecture:** Keep `entry_review_states` and `entry_review_events` as the active review persistence path, but reinterpret them around explicit bucket stages, deterministic prompt cadence, and day-based scheduling. Remove product-visible dependence on floating stability/difficulty, sub-day official buckets, and multi-meaning progression while preserving enough compatibility to migrate existing rows safely and keep existing APIs/frontends operating through a controlled cutover.

**Tech Stack:** FastAPI, SQLAlchemy async models, PostgreSQL, Next.js/React, Playwright, pytest.

---

## 1. Current Repo Findings

### 1.1 Current backend/runtime shape

- Active learner review runtime is centered on [`backend/app/models/entry_review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/models/entry_review.py), [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py), [`backend/app/services/review_prompt_builder.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_prompt_builder.py), and [`backend/app/services/review_submission.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_submission.py).
- Scheduling currently depends on [`backend/app/spaced_repetition.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/spaced_repetition.py), which uses floating `stability`, `difficulty`, prompt-type multipliers, outcome multipliers, and grade multipliers to compute `next_review`.
- Current persistence already has useful concurrency primitives:
  - `submit_queue_review()` locks `EntryReviewState` with `SELECT ... FOR UPDATE`.
  - prompt submissions carry encrypted `prompt_token`s with `prompt_id`, user, queue item, prompt type, answer metadata, and expiry.
  - stale duplicate re-submits are partially handled through `last_submission_prompt_id`.
- Current queue grouping is time-window based, not bucket-stage based:
  - `overdue`
  - `due_now`
  - `later_today`
  - `tomorrow`
  - `this_week`
  - `this_month`
  - `one_to_three_months`
  - `three_to_six_months`
  - `six_plus_months`
- Current manual override options are also time-window oriented and include sub-day:
  - `10m`, `1d`, `3d`, `7d`, `14d`, `1m`, `3m`, `6m`, `never_for_now`

### 1.2 Current prompt/runtime behavior

- There are currently two review modes at runtime:
  - `confidence`
  - `mcq`
- Prompt types currently in active logic:
  - `confidence_check`
  - `audio_to_definition`
  - `definition_to_entry`
  - `sentence_gap`
  - `entry_to_definition`
  - `meaning_discrimination`
  - `typed_recall`
  - `speak_recall`
  - `collocation_check`
  - `situation_matching`
- Prompt selection is not fully deterministic product logic:
  - `ReviewService._select_review_mode()` assigns `confidence` for roughly 1 in 4 cards using a seed derived from item id.
  - `build_available_prompt_types()` depends on user preference toggles and active target count.
  - `_select_prompt_type()` cycles candidates, but the candidate pool itself is driven by adaptive inputs and meaning count.
- Audio fallback is partly present already:
  - prompt audio is loaded conditionally by prompt type.
  - missing audio currently yields `audio_state="not_available"` or placeholder behavior instead of guaranteed prompt-type fallback.

### 1.3 Current multi-meaning behavior

- Current review is meaning-target aware, not entry-primary-meaning-only:
  - `EntryReviewState` stores `target_type` and `target_id`.
  - words use `meaning`, phrases use `phrase_sense`.
  - `_select_active_target_index()` unlocks later meanings/senses based on `success_streak`, `lapse_count`, `entry_type`, and `is_fragile`.
  - `start_learning_entry()` builds multiple learning cards per entry according to `review_depth_preset`.
- This directly conflicts with the V1 requirement to review only the first learner-facing meaning/sense.

### 1.4 Current frontend/runtime behavior

- Learner review UI is primarily [`frontend/src/app/review/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/page.tsx).
- Manual schedule override after success is mediated by the detail page and review session storage:
  - [`frontend/src/components/knowledge-entry-detail-page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/knowledge-entry-detail-page.tsx)
  - [`frontend/src/lib/review-session-storage.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/review-session-storage.ts)
- Review queue pages are built around the current time-window queue buckets:
  - [`frontend/src/app/review/queue/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/queue/page.tsx)
  - [`frontend/src/components/review-queue/review-queue-utils.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-utils.ts)
  - [`frontend/src/components/review-queue/review-queue-shared.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-shared.tsx)
- User settings currently expose more controls than V1 allows:
  - `review_depth_preset` values: `gentle`, `balanced`, `deep`
  - `enable_confidence_check`
  - `enable_word_spelling`
  - `enable_audio_spelling`
  - `show_pictures_in_questions`
- Review depth is surfaced in the learner UI as a banner and settings control, but product naming does not yet match the required `Standard` / `Deep`.

### 1.5 What already matches the target design

- Existing `entry_review_states` / `entry_review_events` are a usable foundation.
- Existing tokenized prompt submission and row locking are the right building blocks for stale-submit and multi-tab protection.
- Existing prompt builder already supports several required V1 prompts:
  - `entry_to_definition`
  - `audio_to_definition`
  - `definition_to_entry`
  - `sentence_gap`
  - `typed_recall`
- Existing phrase and word detail loaders already fetch senses/meanings ordered by `order_index`, so “first meaning only” can be implemented without lexicon schema changes.
- Existing tests and e2e fixtures already cover review, queue, typed recall, confidence, and schedule override flows, which can be repurposed.

### 1.6 What conflicts with the target design

- Floating stability/difficulty materially drives product scheduling today.
- Official schedule currently supports sub-day `10m` and due timestamps that do not align to visible product buckets.
- Current queue and admin queue are organized around time windows, not explicit bucket stages.
- Learning and review flows currently operate on multiple meanings/senses per entry.
- Current settings expose confidence/word spelling/audio spelling as user toggles.
- Current prompt families include extra V1-out-of-scope types:
  - `meaning_discrimination`
  - `collocation_check`
  - `situation_matching`
  - `speak_recall` placeholder
- Current success behavior can preview/reveal, then persist later; this is workable, but the Known safeguard for confidence-only success at `180d` is not explicitly enforced by bucket stage.

## 2. Design Summary

- V1 review is entry-level, first-meaning-only.
- Official stages are explicit bucket stages:
  - `1d`, `2d`, `3d`, `5d`, `7d`, `14d`, `30d`, `90d`, `180d`, `known`
- Standard and Deep affect prompt cadence and hard-prompt eligibility only.
- Success always advances exactly one bucket unless the user overrides to another allowed bucket after success.
- Failure always:
  - shows corrective feedback immediately
  - optionally requeues same-session retry later
  - sets official next review to tomorrow
  - moves bucket back exactly one stage, floor `1d`
- Confidence check is part of Standard/simple prompts, not a standalone mode toggle.
- Typed recall and audio spelling belong only to Deep and only in later stages.
- Known requires objective success from `180d`; confidence-only success cannot graduate to Known.

## 3. Scope / Non-Goals

### In scope

- Replace visible learner review/SRS behavior with deterministic bucket scheduling.
- Collapse active review targeting to the first learner-facing meaning/sense only.
- Redesign prompt cadence for Standard and Deep.
- Align manual override with the same bucket list used by automatic scheduling.
- Update queue/admin queue projections to reflect official bucket stages.
- Remove product-visible dependency on sub-day official scheduling and adaptive interval math.

### Out of scope

- Multi-meaning review or meaning unlock.
- New lexicon schema for per-meaning scheduling in V1.
- Speech-answer production or full voice-recognition implementation.
- New prompt families beyond the required V1 set.
- Broad non-review learner UX redesign outside settings, review, queue, and detail pages.

## 4. Proposed Implementation Architecture

### 4.1 Keep

- `entry_review_states` and `entry_review_events`
- prompt-token flow
- `SELECT ... FOR UPDATE` submission locking
- learner entry status model
- existing word/phrase meaning ordering by `order_index`
- existing detail payload loading for first meaning/sense

### 4.2 Add / reinterpret

- Introduce a canonical stage/bucket module, likely new service helper:
  - `backend/app/services/review_srs_v1.py`
  - source of truth for:
    - bucket order
    - stage groups
    - stage advancement/backoff
    - manual override mapping
    - known-eligibility checks
    - deterministic cadence index selection
- Reinterpret `EntryReviewState` so the product-visible schedule comes from an explicit bucket value rather than `stability`.
- Store explicit cadence state per entry or derive it deterministically from existing counters.

### 4.3 Recommended minimal model strategy

Prefer one additive migration over large schema churn:

- Add `srs_bucket` to `entry_review_states`
- Add `cadence_step` to `entry_review_states`
- Add `official_due_date` or continue using `next_due_at`, but normalize it to day-based scheduling only
- Add `same_session_retry_due_at` or continue using `recheck_due_at` strictly for same-session retry only

Compatibility guidance:

- Keep `stability`, `difficulty`, and `is_fragile` columns temporarily.
- Stop using them for product-visible scheduling.
- Continue writing benign compatibility values during the transition if needed for old code paths, analytics, or rollback safety.

### 4.4 API contract direction

Keep existing review endpoints where possible and revise payload semantics rather than replacing the route surface:

- `GET /api/reviews/queue/due`
- `POST /api/reviews/queue/{id}/submit`
- `POST /api/reviews/queue/{id}/schedule`
- grouped queue/admin queue endpoints

Adjust contracts to expose:

- explicit `srs_bucket`
- visible next bucket recommendation
- manual override options based on the fixed bucket list
- stable prompt metadata that includes `prompt_family`, `prompt_type`, `objective_required_for_known`

## 5. Backend Changes

### 5.1 SRS engine replacement

Primary files:

- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)
- Modify: [`backend/app/services/review_submission.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_submission.py)
- Add: [`backend/app/services/review_srs_v1.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_srs_v1.py)
- Deprecate usage of: [`backend/app/spaced_repetition.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/spaced_repetition.py)

Planned backend rules:

- Success:
  - current bucket `-> next bucket`
  - if current bucket is `180d`, only objective success can move to `known`
  - confidence success at `180d` stays at `180d` or advances to a recommended non-Known handling path defined in the implementation, but must not mark Known
- Failure:
  - new official bucket = previous bucket minus one, floor `1d`
  - `next_due_at = tomorrow`
  - `recheck_due_at` reserved only for same-session retry
- Manual override:
  - allowed only on success
  - selected bucket becomes the official bucket and due date

### 5.2 Prompt-family simplification

Primary files:

- Modify: [`backend/app/services/review_prompt_builder.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_prompt_builder.py)
- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)

V1 prompt families to keep active:

- Simple:
  - `entry_to_definition`
  - `audio_to_definition`
  - `definition_to_entry`
  - `confidence_check`
- Hard for Standard:
  - `sentence_gap`
- Hard for Deep:
  - `sentence_gap`
  - `typed_recall`
  - `audio_spelling` implemented either by reusing `speak_recall` semantics with product renaming or by introducing a new explicit `audio_spelling` prompt type

V1 prompt families to deactivate from selection logic:

- `meaning_discrimination`
- `collocation_check`
- `situation_matching`
- `speak_recall` as a product-visible standalone family unless retained as internal compatibility for “audio spelling”

### 5.3 First-meaning-only targeting

Primary files:

- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)

Implementation approach:

- Word review target is always the first `Meaning` ordered by `Meaning.order_index`.
- Phrase review target is always the first `PhraseSense` ordered by `PhraseSense.order_index`.
- `start_learning_entry()` returns one learning card only.
- `get_due_queue_items()` hydrates the first meaning/sense only.
- ignore `target_type/target_id` unlock logic for later meanings in V1 selection.

Compatibility handling:

- Keep `target_type` / `target_id` columns.
- Continue populating them with the first meaning/sense target for traceability and event joins.
- Stop using `_select_active_target_index()` and related meaning-window logic for learner review behavior.

### 5.4 Queue/admin queue projection changes

Primary files:

- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)
- Modify: [`backend/app/api/reviews.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/api/reviews.py)

New queue bucket labels should reflect official SRS stages rather than time windows. Recommended response groups:

- `1d`
- `2d`
- `3d`
- `5d`
- `7d`
- `14d`
- `30d`
- `90d`
- `180d`
- `known`

Operational rule:

- learner “reviewable now” still depends on due timestamp `<= now`
- grouping label should reflect the item’s official `srs_bucket`, not an arbitrary time window like `this_week`

### 5.5 Settings/API simplification

Primary files:

- Modify: [`backend/app/api/user_preferences.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/api/user_preferences.py)
- Modify: [`backend/app/models/user_preference.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/models/user_preference.py)

Target product contract:

- keep only review mode / depth selection:
  - `standard`
  - `deep`
- do not expose:
  - confidence toggle
  - word spelling toggle
  - audio spelling toggle

Migration-compatible approach:

- add new `review_mode` or repurpose `review_depth_preset`
  - `balanced -> standard`
  - `deep -> deep`
  - `gentle -> standard`
- retain old toggle columns short-term for rollback compatibility
- stop reading those toggles in prompt selection logic

## 6. Frontend Changes

### 6.1 Learner review page

Primary files:

- Modify: [`frontend/src/app/review/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/page.tsx)
- Modify: [`frontend/src/lib/review-session-storage.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/review-session-storage.ts)

Required changes:

- remove assumptions that a learning/relearn pass may span multiple meanings
- render deterministic prompt family behavior for Standard vs Deep
- ensure failure path:
  - shows corrective feedback
  - may resurface same item later in the session
  - does not imply sub-day official schedule
- keep typed answer UX only for Deep hard prompts

### 6.2 Detail page manual override

Primary files:

- Modify: [`frontend/src/components/knowledge-entry-detail-page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/knowledge-entry-detail-page.tsx)

Required changes:

- manual override list must exactly match official bucket list
- override available only after success
- no override UI after wrong / lookup / reveal-before-solving outcomes
- selected bucket copy should align with visible stage language, not relative ad hoc labels

### 6.3 Review queue pages

Primary files:

- Modify: [`frontend/src/app/review/queue/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/queue/page.tsx)
- Modify: [`frontend/src/components/review-queue/review-queue-utils.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-utils.ts)
- Modify: [`frontend/src/components/review-queue/review-queue-shared.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-shared.tsx)
- Modify: [`frontend/src/lib/knowledge-map-client.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/knowledge-map-client.ts)

Required changes:

- replace current time-window queue labels with official bucket-stage labels
- ensure “Start review” actions are based on due status, not bucket name alone
- update admin queue debug and history display to reflect bucket-stage scheduling

### 6.4 Settings page

Primary files:

- Modify: [`frontend/src/app/settings/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/settings/page.tsx)
- Modify: [`frontend/src/lib/user-preferences-client.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/user-preferences-client.ts)

Required changes:

- rename learner choice to `Standard` / `Deep`
- remove confidence/word spelling/audio spelling toggles from the learner UI
- preserve non-review settings like accent, translation, and pictures unless product decides otherwise

## 7. Data Model / Migration Impact

### 7.1 Existing fields to keep using

- `EntryReviewState.user_id`
- `EntryReviewState.entry_type`
- `EntryReviewState.entry_id`
- `EntryReviewState.target_type`
- `EntryReviewState.target_id`
- `EntryReviewState.last_prompt_type`
- `EntryReviewState.last_submission_prompt_id`
- `EntryReviewState.last_outcome`
- `EntryReviewState.success_streak`
- `EntryReviewState.lapse_count`
- `EntryReviewState.exposure_count`
- `EntryReviewState.times_remembered`
- `EntryReviewState.last_reviewed_at`
- `EntryReviewState.next_due_at`
- `EntryReviewState.recheck_due_at` as same-session retry only
- `EntryReviewEvent` analytics fields

### 7.2 Fields that become obsolete or informational only

- `EntryReviewState.stability`
- `EntryReviewState.difficulty`
- `EntryReviewState.is_fragile`

Plan:

- stop using them for scheduling decisions
- optionally continue writing compatibility values during rollout
- mark them deprecated in code comments and plan follow-up removal only after the new runtime is stable

### 7.3 Likely new fields

- `EntryReviewState.srs_bucket`
- `EntryReviewState.cadence_step`
- optional `EntryReviewState.review_mode` if per-entry mode snapshot is needed for analytics/debugging

### 7.4 DB migration recommendation

One additive migration is recommended. Do not remove old fields in the same migration.

Recommended migration scope:

- add `srs_bucket VARCHAR(...) NOT NULL DEFAULT '1d'`
- add `cadence_step INTEGER NOT NULL DEFAULT 0`
- backfill existing rows by mapping `next_due_at` / `stability` / learner status to the nearest official bucket
- set `known` status rows to `srs_bucket='known'`

## 8. Deterministic Cadence Design

### 8.1 Official stage groups

- Stage 1: `1d`, `2d`, `3d`
- Stage 2: `5d`, `7d`, `14d`
- Stage 3: `30d`, `90d`, `180d`
- Known: `known`

### 8.2 Standard cadence

- Stage 1 sequence:
  - `simple`
- Stage 2 sequence:
  - `simple`
  - `simple`
  - `hard`
- Stage 3 sequence:
  - `hard`
  - `simple`
  - `hard`

### 8.3 Deep cadence

- Stage 1 sequence:
  - `simple`
  - `simple`
  - `hard`
- Stage 2 sequence:
  - `hard`
  - `simple`
  - `hard`
- Stage 3 sequence:
  - `hard`
  - `hard`
  - `simple`

### 8.4 Concrete prompt pools

- Simple pool:
  - `entry_to_definition`
  - `audio_to_definition` when audio exists
  - `definition_to_entry`
  - `confidence_check`
- Standard hard pool:
  - `sentence_gap`
- Deep hard pool by stage:
  - Stage 1:
    - `sentence_gap`
  - Stage 2:
    - `sentence_gap`
    - `typed_recall` optional if judged acceptable after backend/frontend fixture review
  - Stage 3:
    - `sentence_gap`
    - `typed_recall`
    - `audio_spelling` when audio exists

### 8.5 Prompt repetition rule

Deterministic selection should be two-layered:

- layer 1: cadence chooses `simple` or `hard`
- layer 2: within that family, choose the first valid prompt type that is not equal to `last_prompt_type`

If only one valid prompt exists, reuse it. No randomness required.

### 8.6 Missing audio fallback

If the chosen prompt family resolves to an audio-dependent prompt and no suitable asset exists:

- fall back within the same difficulty family
- preserve non-repetition rule when possible
- never send a broken prompt payload with empty audio

Example:

- desired `audio_to_definition`, no audio:
  - fall back to `entry_to_definition` or `definition_to_entry` depending on the family rotation
- desired `audio_spelling`, no audio:
  - fall back to `typed_recall`, then `sentence_gap`

## 9. SRS Advancement Rules

### 9.1 Bucket list

1. `1d`
2. `2d`
3. `3d`
4. `5d`
5. `7d`
6. `14d`
7. `30d`
8. `90d`
9. `180d`
10. `known`

### 9.2 Success

- `1d -> 2d`
- `2d -> 3d`
- `3d -> 5d`
- `5d -> 7d`
- `7d -> 14d`
- `14d -> 30d`
- `30d -> 90d`
- `90d -> 180d`
- `180d -> known` only on objective success

### 9.3 Failure

- official next review date = tomorrow
- bucket drops exactly one stage:
  - `1d -> 1d`
  - `2d -> 1d`
  - `3d -> 2d`
  - `5d -> 3d`
  - `7d -> 5d`
  - `14d -> 7d`
  - `30d -> 14d`
  - `90d -> 30d`
  - `180d -> 90d`

### 9.4 Known safeguard

- `180d + confidence_check + "I remember"` must not mark Known
- `180d + objective prompt success` may mark Known

Objective prompts:

- `entry_to_definition`
- `audio_to_definition`
- `definition_to_entry`
- `sentence_gap`
- `typed_recall`
- `audio_spelling`

## 10. Manual Override Behavior

- available only after success
- never available after fail / lookup / reveal-before-solving
- options must exactly be:
  - `1d`, `2d`, `3d`, `5d`, `7d`, `14d`, `30d`, `90d`, `180d`, `known`
- override sets both:
  - official bucket
  - official due date
- override must not mutate hidden latent state that later changes visible behavior

Compatibility note:

- current `schedule_override` API can stay, but enum values and labels must change to the official bucket list

## 11. Safety / Security / Concurrency Review

### 11.1 Correctness risks

- Bucket migration may incorrectly map existing states if it relies only on floating `stability`.
- First-meaning-only cutover may leave old target rows pointing at non-primary meanings.
- Confidence prompts at `180d` could incorrectly mark Known unless explicitly guarded in submission logic.

### 11.2 Stale submission risks

- Same user can open the same item in multiple tabs.
- Current token/idempotency handling is partial; old prompt tokens can still arrive after state has advanced.

Recommended guard:

- reject submit if prompt token `prompt_id` does not match the currently issued prompt for that queue item, or if the queue item version advanced since prompt issue
- alternatively add a monotonic `prompt_generation` or `state_version` field to `EntryReviewState`

### 11.3 Multi-tab / multi-device behavior

- `SELECT ... FOR UPDATE` is good but not sufficient alone for stale logical submissions.
- Need explicit stale-submit detection so tab B cannot overwrite tab A’s newer result with an older prompt token.

### 11.4 Multi-user isolation

- current schema is properly user-scoped
- tests should continue validating same entry reviewed by different users remains isolated

### 11.5 Async / thread safety

- service logic is request-scoped and DB-backed
- avoid in-memory cadence counters or session-only SRS state
- all official state transitions must be persisted transactionally

### 11.6 Security

- keep prompt token user/queue item binding
- keep auth checks on all review endpoints
- avoid exposing correct answers in client payloads
- continue rejecting malformed schedule override values at request validation boundary

### 11.7 Debuggability

- add structured logs on review submit:
  - previous bucket
  - next bucket
  - due date
  - prompt type
  - success/failure
  - manual override yes/no
- add explicit analytics/event fields for objective-vs-confidence graduation decisions

## 12. Performance / Scale Considerations

- Current review workload is simple per-user queue access; hundreds of parallel users should be safe if:
  - index on `(user_id, is_suspended, next_due_at)`
  - same-session retry queries continue to use an indexed field
  - first-meaning hydration is reduced to one meaning/sense per entry, which lowers query cost versus current multi-meaning logic
- Removing adaptive multi-meaning logic should reduce prompt-building and hydration overhead.
- Queue grouping by explicit bucket is cheaper and easier to reason about than repeated time-window classification logic.

## 13. Test Plan

### Unit tests

- bucket advancement/backoff table
- stage-group resolution
- cadence resolution by bucket and review mode
- prompt-family selection with no-repeat rule
- missing-audio fallback
- Known safeguard logic

Primary files:

- Modify or add tests in [`backend/tests/test_review_service.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_service.py)
- Add targeted tests for new helper in [`backend/tests/test_review_service.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_service.py) or a new `backend/tests/test_review_srs_v1.py`

### Service tests

- `get_due_queue_items()` first-meaning-only hydration
- `submit_queue_review()` success/failure/manual override behavior
- stale submit rejection
- same-session retry scheduling separate from official bucket

### API tests

- queue due payloads expose new bucket semantics
- schedule override enum validation
- no manual override after fail
- Known graduation safeguard through submit endpoint

Primary file:

- Modify: [`backend/tests/test_review_api.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_api.py)

### Frontend tests

- settings page exposes Standard/Deep only
- review page renders correct prompt UIs for deterministic cadence
- detail page override options reflect fixed bucket list
- queue pages show official bucket labels

Primary files:

- Modify: [`frontend/src/app/review/__tests__/page.test.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/__tests__/page.test.tsx)
- Modify: [`frontend/src/app/settings/__tests__/page.test.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/settings/__tests__/page.test.tsx)
- Modify: [`frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx)
- Modify queue page tests under [`frontend/src/app/review/queue/__tests__`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/queue/__tests__)

### E2E tests

- adapt existing smoke/full review tests to deterministic buckets and first-meaning-only behavior
- expand fixtures to seed explicit buckets, cadence position, and stale prompt scenarios

Primary files:

- Modify: [`e2e/tests/helpers/review-scenario-fixture.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/helpers/review-scenario-fixture.ts)
- Modify: [`e2e/tests/helpers/review-seed.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/helpers/review-seed.ts)
- Modify: [`e2e/tests/smoke/user-review-submit.smoke.spec.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/smoke/user-review-submit.smoke.spec.ts)
- Modify: [`e2e/tests/full/user-review-queue-srs.full.spec.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/full/user-review-queue-srs.full.spec.ts)

## 14. Detailed E2E Scenarios

1. Standard Stage 1 success progression
   - seed entry at `1d`
   - first prompt is simple
   - success moves `1d -> 2d`
   - later successes move `2d -> 3d -> 5d`

2. Standard Stage 2 cadence
   - seed entry at `5d`
   - three successive due reviews produce cadence `simple, simple, hard`
   - each success advances exactly one bucket

3. Standard Stage 3 cadence
   - seed entry at `30d`
   - cadence is `hard, simple, hard`
   - success advances one bucket only
   - at `180d`, confidence-only success does not mark Known

4. Deep Stage 1 cadence
   - seed entry at `1d`
   - cadence is `simple, simple, hard`
   - hard pool at this stage does not force early typed/audio if the implementation chooses sentence-gap-only
   - advancement remains `+1`

5. Deep Stage 2 cadence
   - seed entry at `7d`
   - cadence is `hard, simple, hard`
   - hard prompts include deterministic eligible pool
   - behavior remains deterministic across runs

6. Deep Stage 3 cadence
   - seed entry at `30d`
   - cadence is mostly hard
   - hard pool includes typed recall and audio spelling when assets exist
   - successes move `30d -> 90d -> 180d -> known`

7. Failure handling
   - seed entry at `14d`
   - user fails
   - corrective feedback shown immediately
   - item may reappear later same session
   - official next review becomes tomorrow
   - bucket becomes `7d`

8. Manual override after success
   - seed entry at `7d`
   - user succeeds
   - override list displays fixed bucket list
   - user selects `30d`
   - official next stage becomes `30d`

9. No manual override after fail
   - seed entry at `30d`
   - user fails
   - override UI not available
   - official next stage becomes `14d`
   - due date is tomorrow

10. Known safeguard
   - seed entry at `180d`
   - confidence check “I remember” does not move to Known
   - objective success on a non-confidence prompt does move to Known

11. Missing audio fallback
   - seed audio-capable prompt target without audio
   - system falls back to another valid prompt in the same family
   - no empty/broken audio payload is sent

12. Multi-user isolation
   - two users review the same entry
   - bucket changes remain isolated by `user_id`

13. Same-user multi-tab stale submit
   - open same due item in two tabs
   - tab A submits first and advances state
   - tab B submits stale prompt token
   - stale request is rejected or ignored safely
   - final state remains correct

14. Session retry vs official schedule
   - fail an item
   - see same item again later in the session
   - official bucket/due remains tomorrow and prior-bucket-minus-one

15. Frontend settings behavior
   - switching Standard/Deep changes cadence and hard prompt availability
   - visible bucket list and success/fail rules remain unchanged

## 15. Rollout Plan

### 15.1 Feature flag

Recommended:

- add a backend/frontend flag such as `REVIEW_SRS_V1_ENABLED`
- route prompt selection and submit scheduling through the new logic only when enabled
- retain old logic for rollback during development and QA

### 15.2 Migration / backfill

- run additive DB migration first
- backfill `srs_bucket` by mapping existing rows to nearest official bucket
- reset `cadence_step` to `0` for all migrated states
- for rows marked known via `LearnerEntryStatus.status='known'`, set bucket `known`

### 15.3 Observability

- log and dashboard:
  - prompt type frequency by mode/stage
  - success/fail rate by bucket
  - manual override frequency
  - stale-submit rejection count
  - missing-audio fallback count

### 15.4 Rollback

- keep old columns and old scheduling module during the first rollout
- feature flag off should revert routing to old behavior
- do not drop deprecated fields or old enum handling until after stable production evidence

## 16. Open Questions / Tradeoffs

1. Whether `audio_spelling` should reuse `speak_recall` with renamed UI text or become a new explicit prompt type.
2. Whether Deep Stage 2 should enable typed recall immediately or reserve it for Stage 3 only.
3. Whether `known` should remain visible in grouped queue/admin queue responses or move to a separate stats-only concept once official review is complete.
4. Whether old “already knew” detail-page behavior should map directly to `known` or require the same `180d` safeguard when invoked from review-derived flows.

## Stage-by-Stage Implementation Plan

### Stage 1: Lock the V1 SRS model and migration contract

**Likely files**

- Add: [`backend/app/services/review_srs_v1.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_srs_v1.py)
- Add: `backend/alembic/versions/<new>_add_srs_bucket_and_cadence_step.py`
- Modify: [`backend/app/models/entry_review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/models/entry_review.py)
- Modify: [`backend/tests/test_review_service.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_service.py)

**Acceptance criteria**

- Bucket order, advancement, backoff, Known safeguard, and cadence logic exist in one explicit module.
- Additive migration exists with a clear backfill mapping.
- Unit tests cover bucket math and deterministic cadence.

### Stage 2: Cut backend prompt selection to first-meaning-only deterministic V1

**Likely files**

- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)
- Modify: [`backend/app/services/review_prompt_builder.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_prompt_builder.py)
- Modify: [`backend/tests/test_review_service.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_service.py)

**Acceptance criteria**

- Only first meaning/sense is selected for learning and due review.
- Active prompt pool matches V1 scope.
- Prompt cadence is deterministic and avoids prompt repetition where alternatives exist.
- Missing audio falls back safely.

### Stage 3: Cut backend submission/queue/admin queue to bucket-stage semantics

**Likely files**

- Modify: [`backend/app/services/review_submission.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_submission.py)
- Modify: [`backend/app/services/review.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review.py)
- Modify: [`backend/app/api/reviews.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/api/reviews.py)
- Modify: [`backend/tests/test_review_api.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_api.py)

**Acceptance criteria**

- Success/failure/manual override follow fixed bucket rules.
- Queue grouping reflects official bucket stages.
- Same-session retry is separated from official schedule.
- Known safeguard is enforced through the submit endpoint.

### Stage 4: Simplify settings and learner-facing review UI

**Likely files**

- Modify: [`backend/app/api/user_preferences.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/api/user_preferences.py)
- Modify: [`backend/app/models/user_preference.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/models/user_preference.py)
- Modify: [`frontend/src/lib/user-preferences-client.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/user-preferences-client.ts)
- Modify: [`frontend/src/app/settings/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/settings/page.tsx)
- Modify: [`frontend/src/app/review/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/page.tsx)
- Modify: [`frontend/src/components/knowledge-entry-detail-page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/knowledge-entry-detail-page.tsx)

**Acceptance criteria**

- Settings show Standard/Deep only for review difficulty.
- Review page behavior matches deterministic V1 prompt cadence.
- Manual override UI exposes only official buckets and only after success.

### Stage 5: Update queue/admin queue frontend and analytics/debug output

**Likely files**

- Modify: [`frontend/src/app/review/queue/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/review/queue/page.tsx)
- Modify: [`frontend/src/components/review-queue/review-queue-utils.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-utils.ts)
- Modify: [`frontend/src/components/review-queue/review-queue-shared.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/components/review-queue/review-queue-shared.tsx)
- Modify: [`frontend/src/lib/knowledge-map-client.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/lib/knowledge-map-client.ts)
- Modify admin queue pages/tests under [`frontend/src/app/admin/review-queue`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/frontend/src/app/admin/review-queue)

**Acceptance criteria**

- Queue labels match official bucket stages.
- Start-review actions still work only for due items.
- Admin queue remains a useful QA/debug surface under the new model.

### Stage 6: Harden concurrency, stale-submit handling, and regression coverage

**Likely files**

- Modify: [`backend/app/services/review_submission.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/app/services/review_submission.py)
- Modify: [`backend/tests/test_review_service.py`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/backend/tests/test_review_service.py)
- Modify: [`e2e/tests/helpers/review-scenario-fixture.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/helpers/review-scenario-fixture.ts)
- Modify: [`e2e/tests/full/user-review-queue-srs.full.spec.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/full/user-review-queue-srs.full.spec.ts)
- Modify: [`e2e/tests/smoke/user-review-submit.smoke.spec.ts`](/Users/johnson/AI/src/words-v2/.worktrees/plan-review-srs-redesign/e2e/tests/smoke/user-review-submit.smoke.spec.ts)

**Acceptance criteria**

- Stale multi-tab submit is rejected or ignored safely.
- Same-user/multi-user concurrency scenarios are covered.
- Required smoke/full review tests pass against the new deterministic system.

