# Entry Review System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current meaning-level review experience with an entry-first review flow for words and phrases, including adaptive scheduling, detail reveal, and relearn fallback.

**Architecture:** Keep the existing `/reviews` backend surface and queue/history persistence as the compatibility layer for now, but introduce a new entry-review contract on top of it. The backend will group queue items and learning payloads by entry, generate richer prompt metadata plus reveal/scheduling payloads, and interpret outcomes using the new entry-review semantics. The frontend review page will move from a flat “submit and advance” card flow to a session state machine with challenge, lookup/relearn, reveal card, and interval override states.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Next.js App Router, React, TypeScript

---

### Task 1: Add the entry-review design and compatibility contract

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`
- Modify: `frontend/src/lib/knowledge-map-client.ts`
- Modify: `frontend/src/app/review/page.tsx`

**Step 1: Define the new API response/request shapes**

Add explicit response models and frontend types for:
- prompt outcome semantics: `correct_tested`, `remember`, `lookup`, `wrong`
- reveal card payloads with primary definition, examples, other meanings count, nuance/compare sections, remembered count
- recommended schedule choices with one flagged default option
- relearn payloads and “needs_relearn” / “recheck_planned” flags

**Step 2: Preserve compatibility with the existing queue/history tables**

Do not introduce a migration in this slice. Use the current queue/history rows for persistence, but expose them through entry-level contracts by:
- grouping word queue items under one entry
- deriving phrase review payloads from phrase senses
- treating submit events as entry-review outcomes even if the stored queue row remains meaning-backed

**Step 3: Document temporary limitations in code comments**

Leave clear comments at the backend seam that:
- scheduling is now entry-oriented in API semantics
- persistence is still meaning/history-backed until a later migration
- phrases use derived runtime review payloads rather than persisted queue rows

### Task 2: Replace SM-2 semantics with the adaptive entry scheduler

**Files:**
- Modify: `backend/app/spaced_repetition.py`
- Modify: `backend/app/services/review.py`

**Step 1: Replace the SM-2 result object**

Introduce an entry-review scheduling result that carries:
- `outcome`
- `stability`
- `difficulty`
- `interval_days`
- `next_review`
- `is_fragile`

**Step 2: Implement the adaptive interval calculation**

Base the scheduler on:
- outcome factor
- context factor from prompt type
- difficulty factor
- manual override resolution

Use the agreed defaults:
- `correct_tested = 2.2`
- `remember = 1.6`
- `lookup = 0.6`
- `wrong = 0.35`

And prompt/context factors:
- sentence gap `1.10`
- definition to word `1.05`
- audio `1.00`
- word to definition `0.95`
- meaning discrimination `1.08`

**Step 3: Bridge old persistence fields to new semantics**

Map current stored fields as follows:
- persisted `ease_factor` becomes temporary carrier for `difficulty`
- persisted `interval_days` remains interval days
- persisted `repetitions` becomes temporary remembered/success count proxy where needed

Keep the translation logic isolated in service helpers so a later schema migration can remove it cleanly.

### Task 3: Generate entry-first prompts and reveal cards

**Files:**
- Modify: `backend/app/services/review.py`
- Modify: `backend/app/api/reviews.py`
- Read-only reference: `backend/app/api/knowledge_map.py`

**Step 1: Add prompt families for entry review**

Support these prompt types in the review service:
- `audio_to_definition`
- `definition_to_entry`
- `sentence_gap`
- `entry_to_definition`
- `meaning_discrimination` placeholder contract

The initial implementation must ship the first four and reserve the fifth type in the contract.

**Step 2: Build entry detail payloads**

For words, derive reveal content from:
- primary meaning
- remaining meanings count
- first example
- part of speech

For phrases, derive reveal content from:
- primary sense
- remaining senses count
- first example
- phrase text

Include placeholders for:
- `audio_state`
- `compare_with`
- `pro_tips`

**Step 3: Add relearn payload generation**

When the user chooses `Lookup` or gets an answer wrong, return a relearn payload containing:
- hero entry metadata
- primary meaning
- all meanings/senses summary
- one mini-check prompt for re-entry into review

### Task 4: Add entry-review endpoints/submit semantics

**Files:**
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/services/review.py`

**Step 1: Expand queue due payloads**

Change `/reviews/queue/due` to return:
- entry identity
- prompt type
- challenge prompt
- reveal payload
- recommended schedule options

**Step 2: Expand queue submit payloads**

Change `/reviews/queue/{id}/submit` to accept:
- `outcome`
- `prompt_type`
- `selected_option_id`
- `typed_answer`
- `schedule_override`

Response should return:
- resolved outcome
- updated interval
- reveal card
- `needs_relearn`
- `recheck_planned`

**Step 3: Expand learning start payloads**

Change `/reviews/entry/{entry_type}/{entry_id}/learning/start` from “all meanings as cards” to “entry learning payload”:
- ordered review cards
- relearn/review detail payload
- lookup hint metadata

### Task 5: Rebuild the frontend review page as a state machine

**Files:**
- Modify: `frontend/src/app/review/page.tsx`
- Modify: `frontend/src/lib/knowledge-map-client.ts`

**Step 1: Replace flat card progression with explicit phases**

Use phases:
- `idle`
- `challenge`
- `relearn`
- `reveal`
- `completed`

**Step 2: Implement prompt rendering by prompt family**

Render:
- audio prompt with placeholder play control
- definition prompt
- sentence-gap prompt
- entry-to-definition prompt

Keep the UI mobile-first and structurally close to the recording:
- top progress
- large challenge area
- A-D answer buttons
- bottom confidence actions

**Step 3: Add reveal card and schedule selection**

After success or `I remember`, show:
- headword/phrase
- primary definition
- example
- “other meanings” summary
- remembered count
- schedule selector with the backend-provided default

**Step 4: Add relearn fallback**

After wrong/lookup:
- show the relearn card
- show all meanings/senses summary
- show “Review now” / continue action

### Task 6: Update live project status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update the review workstream entry**

Record that:
- review semantics are being moved to entry-level
- the frontend now follows challenge -> reveal -> schedule/relearn
- persistence is still on the existing queue/history compatibility layer if that remains true after implementation

**Step 2: Add a dated status log note**

Include evidence references to:
- updated API/service files
- updated review page
- this plan doc

### Task 7: Deferred follow-up after this slice

**Files:**
- Future: new migration + dedicated entry-review tables

**Step 1: Reserve the next migration scope**

Future schema should introduce first-class entry-review persistence:
- entry queue table
- entry review event table
- explicit `stability` and `difficulty`
- recheck/relearning state

**Step 2: Reserve richer prompt families**

Future prompt types:
- meaning discrimination
- collocation check
- situation matching
- typed recall

### Task 8: Align repository verification and CI with the shipped review surface

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/status/project-status.md`

**Step 1: Make PR E2E gating match the required quality bar**

Replace the split smoke/full PR story with one required Playwright job that:
- boots the full app stack
- applies migrations
- runs the full E2E suite on every pull request
- uploads one unified E2E artifact bundle

**Step 2: Re-run the same surfaces locally**

Verify the same scopes that CI enforces:
- backend lint/test
- learner frontend lint/test/build
- admin frontend lint/test/build
- lexicon pytest/smoke
- full Playwright E2E

**Step 3: Record the CI governance change**

Update live status to note that:
- PRs now run full E2E
- local verification was rerun against the aligned command set
- review workstream gating now matches the implemented learner/admin behavior

Plan complete and saved to `docs/plans/2026-03-27-entry-review-system-implementation.md`.
