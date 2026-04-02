# Ultimate Requirements Prompt — SRS + Review Redesign for `words-v2`

You are working inside the `words-v2` repository.

Do **not** rely on any previous Codex or chat context. Treat this prompt as the full source of requirements, design intent, scope, non-goals, acceptance criteria, and testing expectations. You may inspect the repository to refine implementation details, but you must preserve the decisions and constraints in this document unless you find a concrete repo conflict and document it.

Your job is to:
1. inspect the current repository and write a plan,
2. then implement the redesign in safe stages,
3. verify each stage with tests,
4. update docs/status/plan files as required by the repo,
5. keep the implementation grounded in the current schema and codebase.

---

## 1. Product context

This app is an English vocabulary learning app covering:
- 30k+ words
- 7000+ phrasal verbs and idioms

Each entry may already include:
- multiple definitions / senses
- multiple examples per sense
- pronunciation
- mp3 audio for entry / definition / example scope
- AI-generated pictures per definition, if already supported in the repo

The goal is to design and implement a review system that combines:
- spaced repetition scheduling,
- varied review challenges,
- deep long-term memory,
- low fatigue,
- good support for words, phrasal verbs, and idioms,
- and minimal risk to the existing lexicon database.

This redesign must cover **both**:
- the **SRS / scheduling** system,
- and the **review challenge / prompt** system.

---

## 2. Repository-grounded facts you must respect

You must inspect and confirm the current repo state before coding, but design under these assumptions unless the code clearly proves otherwise:

### 2.1 Existing review schema and service
The repo already has review state/event infrastructure. You should inspect at least:
- `backend/app/models/entry_review.py`
- `backend/app/services/review.py`
- `backend/tests/test_review_models.py`
- `backend/tests/test_review_service.py`
- `backend/tests/test_review_api.py`

Assume the current review layer already includes review state fields such as:
- `entry_type`
- `entry_id`
- `stability`
- `difficulty`
- `success_streak`
- `lapse_count`
- `exposure_count`
- `times_remembered`
- `is_fragile`
- `is_suspended`
- `relearning`
- `relearning_trigger`
- `recheck_due_at`
- `last_reviewed_at`
- `next_due_at`

Assume the current review event layer already includes fields such as:
- `prompt_type`
- `prompt_family`
- `outcome`
- `response_input_mode`
- `response_value`
- `used_audio_placeholder`
- `selected_option_id`
- `scheduled_interval_days`
- `scheduled_by`
- `time_spent_ms`

Assume the current review service already has prompt types similar to:
- `audio_to_definition`
- `definition_to_entry`
- `sentence_gap`
- `entry_to_definition`
- `meaning_discrimination`
- `typed_recall`
- `speak_recall`
- `collocation_check`
- `situation_matching`

Assume the current review service also already supports manual schedule overrides similar to:
- `10m`
- `1d`
- `3d`
- `7d`
- `14d`
- `1m`
- `3m`
- `6m`
- `never_for_now`

### 2.2 Existing lexicon schema
You must inspect at least:
- `backend/app/models/meaning.py`
- `backend/app/models/meaning_example.py`
- `backend/app/models/phrase_entry.py`
- `backend/app/models/phrase_sense.py`
- `backend/app/models/phrase_sense_example.py`
- `backend/app/models/lexicon_voice_asset.py`
- `backend/app/models/word_confusable.py`
- `docs/plans/2026-03-07-lexicon-sense-ranking-design.md`

Assume the current lexicon schema already provides rich sense-level data, for example:
- `Meaning.definition`
- `Meaning.part_of_speech`
- `Meaning.wn_synset_id`
- `Meaning.primary_domain`
- `Meaning.register_label`
- `Meaning.usage_note`
- `Meaning.example_sentence`
- `Meaning.order_index`
- `PhraseSense.definition`
- `PhraseSense.usage_note`
- `PhraseSense.part_of_speech`
- `PhraseSense.register`
- `PhraseSense.primary_domain`
- `PhraseSense.secondary_domains`
- `PhraseSense.grammar_patterns`
- `PhraseSense.synonyms`
- `PhraseSense.antonyms`
- `PhraseSense.collocations`
- `PhraseSense.order_index`

Assume voice assets can already attach to one of:
- word
- meaning
- meaning example
- phrase entry
- phrase sense
- phrase sense example

Assume `word_confusables` already exists and should be preferred over synthetic spelling distractors when available.

### 2.3 Existing frontend/testing setup
You must inspect at least:
- `frontend/package.json`
- `frontend/jest.config.js`
- current review-related frontend files if they exist
- `AGENTS.md`
- `docs/status/project-status.md`

Assume:
- backend tests use `pytest`
- backend `pyproject.toml` points pytest at `tests`
- frontend uses Next.js + React + Zustand + Jest
- repo has an `e2e/` directory and repo docs/testing conventions that must be respected
- `AGENTS.md` and repo docs describe required implementation and verification workflow

---

## 3. Core design decision: how review targets should work

### 3.1 Final review target model for V1
In V1, the actual memory target should be:
- `meaning` for words
- `phrase_sense` for phrasal verbs / idioms / phrases

The parent display container should be:
- `word` for meanings
- `phrase_entry` for phrase_senses

This means:
- learners review a **specific sense**, not only the whole headword,
- but the UI still clearly shows the parent word/phrase as the visible entry.

### 3.2 Why this is the right tradeoff
We need deeper than whole-entry review because knowing one meaning of a word is not the same as knowing all important meanings.

But we should **not** create a new lexicon-level `sense_group` field in V1 because:
- the lexicon detail has already been generated,
- adding grouping metadata to word/phrase rows creates schema risk and backfill complexity,
- grouping without human or LLM review is noisy,
- the current repo already has enough structure to schedule `meaning` and `phrase_sense` directly,
- and fatigue can be solved in the review layer instead.

### 3.3 Explicit V1 rule
Do **not** add `sense_group` fields to:
- `words`
- `meanings`
- `phrase_entries`
- `phrase_senses`

If later metrics prove grouping is necessary, grouping should be added in the **review layer**, not the lexicon layer.

---

## 4. Scope

### 4.1 In scope
You are designing and implementing:
1. sense-level review targeting using the existing review tables,
2. multi-sense fatigue control,
3. adaptive SRS scheduling,
4. challenge selection and prompt building,
5. advanced challenge types,
6. settings that alter review behavior,
7. frontend review UX updates,
8. analytics and event logging,
9. plan/docs/status updates,
10. tests at unit, integration, API, frontend, and end-to-end level.

### 4.2 Out of scope for V1 unless trivial and already aligned
These are **not** primary V1 deliverables:
- inventing new lexicon schema for sense grouping,
- LLM-based sense grouping,
- manual editorial review as a required dependency,
- replacing the whole review system with a rewrite,
- changing unrelated lexicon generation pipelines,
- inventing new image storage schema if images are not already wired,
- broadening `speak_recall`, `collocation_check`, or `situation_matching` unless they fit naturally into the new architecture with minimal additional scope.

---

## 5. Product goals and design principles

The final system must optimize for the following:

### 5.1 Long-term retention, not just short-term success
The system should emphasize spaced retrieval and durable retention rather than passive recognition alone.

### 5.2 Deep knowledge, but not overwhelming review load
The system must balance:
- meaning recognition,
- form recall,
- contextual usage,
- spelling,
- audio recognition,
- and multi-sense coverage,
without flooding the learner.

### 5.3 Progressive difficulty
Early review should lean more on recognition.
Mature review should lean more on contextual recall and typed recall.

### 5.4 Multi-sense coverage without fatigue
A learner should not have to answer 3–4 separate tests for different senses of the same word in one short session.

### 5.5 Context matters more for phrases and idioms
Phrasal verbs and idioms should rely more heavily on context-based review than bare definition matching.

### 5.6 Immediate corrective feedback
Wrong answers should immediately teach, not just punish.

### 5.7 Timing is noisy
Timing can inform difficulty, but it must not be treated as reliable proof of memory because users may be distracted, multitasking, backgrounding the app, or replaying audio.

### 5.8 Backward-compatible evolution
Keep existing review data and flows working where practical. Extend rather than rewrite.

---

## 6. Final SRS design requirements

### 6.1 Scheduling model
The system must support:
- current manual interval overrides (if already present),
- and a new automatic adaptive scheduler.

The automatic scheduler must not be just a hardcoded ladder.
It should use a normalized grade-based memory-state approach.

### 6.2 Normalized grades
All review outcomes must map into one of:
- `fail`
- `hard_pass`
- `good_pass`
- `easy_pass`

### 6.3 Grade inputs
Normalized grades should be derived from:
- objective correctness,
- challenge type,
- hint usage,
- reveal/show-answer usage,
- audio replay count,
- confidence-check result,
- time spent bucket,
- optional user/device interruption signals if available.

### 6.4 Timing rule
`time_spent_ms` is a weak signal only.
It may affect:
- `hard_pass` vs `good_pass` vs `easy_pass`

It must **not** alone decide:
- pass vs fail,
- whether the learner remembered the item,
- whether a mature card should reset.

If possible, timing should be:
- capped,
- ignored when app focus is lost or the interaction is interrupted,
- bucketed coarsely rather than treated as precise truth.

### 6.5 Manual overrides
Keep the current manual schedule overrides working.
If the user chooses a manual override such as `3d` or `never_for_now`, that override must take precedence over the automatic recommendation.
Log that clearly in review events.

### 6.6 Same-day learning/relearning behavior
For new or failed items:
- use same-day retries via `recheck_due_at` or equivalent,
- do not turn the scheduler into a brute-force cram loop,
- requeue missed items after a small buffer (for example after 3–7 other cards or equivalent retry spacing).

### 6.7 Interday review behavior
After an objective success on a new item:
- the first interday review should default to the next day,
- later spacing should be adaptive, not rigid.

### 6.8 Maturity and lapses
A mature item that is failed should:
- lose some stability,
- enter relearning,
- potentially become fragile again,
- but **not** be hard-reset to the same state as a never-learned item.

### 6.9 Stable-learning rule
Do not treat one correct answer as enough to “master” an item.
A sensible default should require multiple successful objective interday reviews before a target is considered stable.

Use these defaults unless the codebase strongly requires a small variation:
- normal target: stable after ~3 successful objective interday reviews
- harder target (idiom, repeated lapse, spelling-heavy): stable after ~4 successful objective interday reviews

### 6.10 Retention presets
Implement configurable review depth presets that influence scheduler and challenge selection:
- `gentle`
- `balanced`
- `deep`

Recommended default retention targets:
- `gentle`: lower workload, easier mix
- `balanced`: default product preset
- `deep`: higher workload, more recall-heavy

If you need numeric defaults, use them in config, not magic constants scattered in services.

---

## 7. Final multi-sense fatigue-control design

This is critical.

### 7.1 No lexicon grouping in V1
Do not add grouping fields to the word database in V1.
Use the existing `order_index` and review logic instead.

### 7.2 Progressive unlock
For a parent entry with multiple meanings/senses:
- initially, only the lowest `order_index` meaning/sense should be active,
- later meanings/senses unlock only after earlier ones have demonstrated enough stability.

### 7.3 Unlock rule
The exact unlock threshold can be implemented using existing review-state fields, but behavior must be equivalent to:
- unlock the next sibling when the current earlier sibling is no longer highly fragile and has shown repeated objective success.

Do not unlock multiple weak siblings too early.

### 7.4 Active-sense caps by preset
At any one time, cap active review targets per parent entry:
- `gentle`: 1 active sense per entry
- `balanced`: 2 active senses per entry
- `deep`: 3 active senses per entry

These are active caps, not total lexicon-sense caps.

### 7.5 Sibling bury rule
After one scored review for an entry in a session/day:
- bury other due sibling meanings/senses until the next day,
- except allow one immediate scaffolded retry after a failure if needed.

This prevents one word from monopolizing a session.

### 7.6 Coverage summary
The product should expose learner-facing progress for multi-sense entries such as:
- `familiar_with_1_meaning`
- `partial_coverage`
- `deep_coverage`

Do **not** define mastery solely as “every lexicon sense is mature.”

### 7.7 Why this design is required
This is the key fatigue-control strategy. It gives per-sense memory without requiring new lexicon grouping metadata.

---

## 8. Final review challenge design

### 8.1 Challenge philosophy
Use a mix of:
- recognition,
- contextual discrimination,
- recall,
- spelling,
- audio,
- metacognitive checks,

but weight them differently by stage and preset.

### 8.2 Canonical challenge families
The final system should support these challenge families.
When possible, map them to the repo’s current prompt types instead of inventing a parallel naming system.

#### A. Meaning recognition from text
Equivalent to current `entry_to_definition`.
- Prompt: word or phrase text
- Response: choose the correct definition / paraphrase
- Use for easier early review, especially new/fragile targets

#### B. Meaning recognition from audio
Equivalent to current `audio_to_definition`.
- Prompt: play audio
- Response: choose the correct definition / paraphrase
- Replay allowed
- Replay count must be recorded

#### C. Form recognition from definition/example
Equivalent to current `definition_to_entry`.
- Prompt: concise definition or short example
- Response: choose the correct word/phrase
- Good bridge from meaning to form

#### D. Context cloze MCQ
Equivalent to current `sentence_gap`.
- Prompt: example sentence with the target omitted
- Response: choose the correct word/phrase
- Must be prioritized for phrasal verbs and idioms

#### E. Meaning discrimination in context
Equivalent to current `meaning_discrimination`.
- Prompt: same parent word/phrase plus context or example
- Response: choose which meaning fits the context
- This is the preferred way to cover multiple meanings without multiplying too many full cards

#### F. Typed recall
Equivalent to current `typed_recall`.
- Prompt: definition or example
- Response: type the word/phrase
- Stronger evidence than MCQ
- Must become more common on developing/mature items

#### G. Spelling contrast MCQ
New or refined challenge.
- Prompt: definition/example/audio-derived need
- Response: correct spelling plus plausible orthographic confusables
- Use `word_confusables` first
- Synthetic near-neighbors only as fallback
- Must not dominate fragile review

#### H. Audio spelling typed
New or refined challenge.
- Prompt: audio
- Response: type the word/phrase
- Use only when enabled or when item difficulty warrants it

#### I. Confidence check
Current repo may already have a confidence-style path.
- Prompt: hidden recall / short context / “do you remember?”
- Response: something like “I recalled it” or “Show me”
- This is weak evidence only
- It must not strongly advance a target by itself

### 8.3 Out-of-scope advanced families unless trivially aligned
These should not become blockers for V1:
- speak recall
- collocation check
- situation matching

They may remain in the codebase, but they are not required to be fully redesigned unless that is already simple and aligned.

### 8.4 Challenge selection policy
Challenge selection must be adaptive.
Do **not** rotate challenge types uniformly at random.

#### For new / fragile items
Prefer:
- meaning recognition from text/audio
- form recognition from definition/example
- light context cloze

Avoid by default:
- heavy spelling
- audio spelling
- too much typed recall

#### For developing items
Increase:
- context cloze
- meaning discrimination
- typed recall

#### For mature items
Favor:
- context cloze
- meaning discrimination
- typed recall
- selective spelling/audio spelling if enabled

Recognition should still exist, but not dominate.

#### For phrasal verbs and idioms
Favor:
- context cloze
- contextual meaning discrimination
- typed recall from example/context

Do not rely mainly on picture matching or bare definition matching.

### 8.5 Anti-fatigue / anti-repetition rules
The selector must enforce:
- do not repeat the same challenge type twice in a row for the same target
- do not present more than 2 high-friction challenges in a row globally if avoidable
- do not keep surfacing sibling senses of one entry back-to-back except immediate retry after fail
- do not overuse pictures or spelling-heavy tasks on mature/abstract items

### 8.6 MCQ option quality rules
For MCQ challenges:
- use 4 options when 3 plausible distractors exist
- fall back to 3 total choices when distractor quality is weak
- distractors should be plausible, not nonsense
- semantic distractors should try to match part of speech / frequency / learner plausibility when appropriate
- spelling distractors should prefer `word_confusables` before synthetic variations

---

## 9. Sense-aware prompt-building requirements

### 9.1 Parent vs target
All prompt building must understand that:
- the visible display entry may be the parent word/phrase,
- the actual memory target is a meaning or phrase_sense.

### 9.2 Ambiguity suppression
If a parent entry has multiple active meanings/senses:
- do **not** generate a bare ambiguous prompt such as plain entry/audio -> definition unless it is disambiguated,
- prefer context-rich prompts instead (`sentence_gap`, `meaning_discrimination`, `typed_recall`, etc.).

### 9.3 Example selection
Use the best current example for the target meaning/sense, respecting existing order rules such as `order_index` where present.

### 9.4 Audio/media resolution order
For prompts that use audio, resolve in this priority order when relevant:
1. example-level audio
2. meaning / phrase_sense-level audio
3. entry-level audio

Do not get stuck using entry-level audio only if more specific audio exists.

### 9.5 Images
If images are already wired in the repo, thread them through carefully.
If not, do not invent new image storage/schema in V1.

### 9.6 Picture usage policy
Pictures should be:
- more common for concrete senses,
- more useful on early-stage review,
- less emphasized for abstract senses, idioms, and mature items,
- more acceptable in feedback than in the initial prompt.

---

## 10. Correct / wrong answer behavior

### 10.1 On wrong answers
On every wrong answer, the system must:
1. mark the result as `fail`,
2. show immediate corrective feedback,
3. show the correct answer,
4. show the tested-sense definition,
5. show one best example,
6. offer audio replay if available,
7. show a picture only if helpful and already supported,
8. log the event,
9. requeue the item for same-session retry after a short buffer,
10. retry with an easier scaffold where possible.

Examples of easier scaffold:
- typed recall fail -> MCQ or first-letter support
- audio spelling fail -> definition_to_entry or entry_to_definition
- sentence_gap fail -> simpler definition_to_entry

### 10.2 On correct answers
Correct answers should be classified into:
- `hard_pass`
- `good_pass`
- `easy_pass`

Interpretation examples:
- correct but slow / many replays / hint used -> `hard_pass`
- correct with normal effort -> `good_pass`
- correct cleanly on a relatively strong challenge -> `easy_pass`

### 10.3 Confidence-only outcomes
A pure confidence-only response should never behave like a strong objective correct answer.

---

## 11. Typed recall and validation rules

### 11.1 Normalization
Typed answers must normalize at least:
- case
- punctuation
- whitespace

### 11.2 Multiword handling
Multiword expressions must be validated as multi-token answers.

### 11.3 Phrasal-verb particle handling
For phrasal verbs, if the learner gets the base verb right but the particle wrong:
- mark incorrect,
- give targeted feedback explaining that the wrong particle changes the phrase.

### 11.4 Acceptable variants
If current data/model supports acceptable variants, use them.
If not, do not invent a broad freeform synonym system in V1.

---

## 12. Settings requirements

Implement durable settings that influence challenge selection and/or scheduling behavior.
At minimum:
- `reviewDepthPreset = gentle | balanced | deep`
- `enableConfidenceCheck`
- `enableWordSpelling`
- `enableAudioSpelling`
- `showPicturesInQuestions`

### 12.1 Preset behavior expectations
#### Gentle
- more recognition
- lower friction
- active sense cap = 1
- fewer typed/spelling challenges

#### Balanced
- default product preset
- mix of recognition, context, and some typed recall
- active sense cap = 2

#### Deep
- more typed/contextual recall
- audio spelling allowed if appropriate
- active sense cap = 3

---

## 13. Analytics and logging requirements

Preserve current review event logging and extend it if needed.
At minimum, make sure the system can analyze:
- accuracy by challenge type
- accuracy by target type (`meaning`, `phrase_sense`, etc.)
- parent entry type (`word` vs `phrase_entry`)
- response input mode
- selected option / distractor confusion
- replay count
- time bucket
- hint/reveal usage
- confidence-check mismatch cases
- mature-card lapse rate
- sense coverage progression
- how often sibling-sense suppression worked or failed

Do not break existing event history if avoidable.
If additional review-layer schema is needed for analytics, justify it clearly and keep it separate from lexicon tables.

---

## 14. Frontend UX requirements

The frontend must make the new review system usable and clear.

### 14.1 General UX
- mobile-first
- large tap targets
- minimal clutter before answer
- richer feedback after answer
- clear parent word/phrase display
- accessible audio replay control
- good typed-input UX

### 14.2 Sense-aware presentation
The UI must show the visible parent entry clearly, while still testing the correct underlying meaning/phrase_sense.
It must not confuse the learner by exposing many sibling meanings at once.

### 14.3 Feedback screen
After answer submission, feedback should present:
- correct answer
- concise definition
- best example
- audio replay if available
- picture if supported and helpful
- optionally a short contrast note when an MCQ distractor was specifically misleading

### 14.4 Settings UX
Users must be able to modify review settings and see those changes affect subsequent review selection.
Settings must persist.

---

## 15. Explicit non-goals and “do not do this” list

Do **not** do the following in V1 unless absolutely required and justified:
- do not add `sense_group` fields to lexicon tables
- do not depend on LLM/manual sense grouping
- do not rewrite the entire review subsystem from scratch
- do not make timing the main signal for memory strength
- do not make confidence-only responses strong promotion signals
- do not heavily use spelling/audio-spelling on fragile items by default
- do not force all meanings of a word active at once
- do not invent new image schema if the repo does not already support image plumbing
- do not break current manual schedule overrides
- do not break existing word/phrase review flows if backward compatibility is feasible

---

## 16. Required implementation workflow

### 16.1 Phase 0 — inspect and plan first
Before non-trivial coding:
1. inspect the repo files listed above,
2. inspect `AGENTS.md` and follow it,
3. create/update a plan file in `docs/plans/` with:
   - goals
   - non-goals
   - staged implementation plan
   - risks
   - acceptance criteria
   - test strategy
4. update `docs/status/project-status.md` if repo policy requires status updates for this feature.

### 16.2 Phase 1 — review target extension
Implement meaning/phrase_sense review targets using existing review tables and current services.

### 16.3 Phase 2 — multi-sense fatigue control
Implement progressive unlock, active caps, sibling burying, and coverage summaries.

### 16.4 Phase 3 — adaptive scheduler and grade mapping
Refactor scheduling into normalized grade -> scheduler update while preserving manual overrides.

### 16.5 Phase 4 — sense-aware prompt builders and media fallback
Make prompt generation safe, sense-aware, and media-aware.

### 16.6 Phase 5 — advanced challenge types
Implement/refine typed recall, spelling contrast, audio spelling, confidence check.

### 16.7 Phase 6 — frontend integration and settings
Update frontend review flows, feedback, settings, persistence, analytics wiring.

### 16.8 Phase 7 — hardening
Run regression tests, cleanup, update docs, and prepare rollout notes.

---

## 17. Testing strategy

You must provide both:
- implementation tests by layer,
- end-to-end acceptance tests by user behavior.

### 17.1 Backend/unit/integration tests
At minimum, add or update tests that cover:

#### Review target model
- `meaning` and `phrase_sense` can be used as review targets
- parent word / parent phrase_entry resolution works
- old `word` and `phrase` entry types still behave safely if still supported

#### Multi-sense fatigue control
- only earliest `order_index` is active initially
- unlock occurs only after threshold
- active-sense caps are enforced by preset
- sibling burying occurs after one scored review
- one immediate retry after failure can bypass sibling bury
- coverage summary updates correctly

#### Scheduler and grading
- `good_pass` schedules later than `hard_pass`
- `easy_pass` schedules later than `good_pass`
- `fail` creates relearning/recheck behavior
- mature-card lapse does not hard-reset all history
- manual override wins when chosen
- extreme `time_spent_ms` is capped/ignored as weak evidence

#### Prompt building
- meaning and phrase_sense prompts use correct definition/example
- ambiguity suppression blocks unsafe bare prompts on multi-sense entries
- example ordering respects `order_index`
- audio resolution prefers example > sense > entry
- distractors are coherent and exclude the correct answer

#### Advanced validation
- typed recall normalization works
- multiword validation works
- phrasal-verb particle mistakes get targeted feedback
- spelling distractors prefer `word_confusables`
- fragile items do not get spelling-heavy prompts unless enabled
- confidence check affects schedule less than objective correct answers

### 17.2 Frontend tests
At minimum, add/update frontend tests that cover:
- review settings persist
- MCQ flow works
- typed recall flow works
- audio replay works
- corrective feedback renders correctly
- challenge progression reflects backend rules and does not visibly spam sibling senses
- settings visibly alter prompt behavior

### 17.3 API contract tests
At minimum, cover:
- fetching a due review target returns correct target + parent display info
- submitting review answers logs correct event metadata
- retry/requeue state is correctly reflected in subsequent API responses
- manual overrides are respected in API submissions

---

## 18. Well-defined end-to-end acceptance test cases

Implement these as end-to-end tests if practical with the repo’s existing harness, or as the closest realistic integration/e2e equivalent if not.

### E2E-01 — New single-sense word enters review
**Given** a user has learned a word with one meaning and no prior review state
**When** the system introduces the first review card and the user answers correctly
**Then** a review state is created for the `meaning` target, not only the parent word
**And** the UI shows the parent word clearly
**And** the next review is scheduled for the next day or equivalent first interday step
**And** a review event is logged with prompt type, outcome, and scheduled interval metadata

### E2E-02 — Multi-sense word unlocks progressively
**Given** a word with at least 4 meanings ordered by `order_index`
**And** the user has only stabilized the first meaning
**When** the due queue is generated
**Then** only the first meaning is active at first
**And later**, after repeated success, the next sibling meaning unlocks
**And** the active-sense cap for the chosen preset is respected

### E2E-03 — Sibling senses are buried after one scored review
**Given** a word with two active meanings both due today
**When** the user completes one scored review for that entry
**Then** the sibling meaning is not shown again in the same short session/day
**Unless** this is an immediate scaffolded retry caused by a failure

### E2E-04 — Phrase/idiom prefers context-rich review
**Given** a phrasal verb or idiom with multiple senses and examples
**When** a review card is generated for an active phrase_sense
**Then** the system prefers `sentence_gap`, `meaning_discrimination`, or context-rich `typed_recall`
**And** it avoids an unsafe bare prompt that would be ambiguous without context

### E2E-05 — Wrong answer triggers corrective feedback and buffered retry
**Given** a due review card
**When** the user answers incorrectly
**Then** the system shows immediate corrective feedback including correct answer, tested-sense definition, best example, and audio if available
**And** the target is marked `fail`
**And** the target is scheduled for same-session retry after a short buffer
**And** the retry uses an easier scaffold where possible

### E2E-06 — Mature item lapse does not hard-reset
**Given** a mature target with high stability and several successful past reviews
**When** the user fails a difficult recall challenge
**Then** the target enters relearning / fragile behavior
**And** stability is reduced
**But** history is preserved and the target is not treated as brand new

### E2E-07 — Audio fallback uses the most specific available asset
**Given** an example-driven prompt with example-level audio available
**When** the prompt is rendered
**Then** example-level audio is used
**And if missing**, meaning/phrase_sense audio is used
**And if still missing**, entry-level audio is used

### E2E-08 — Typed recall normalization and phrasal-verb particle feedback
**Given** the target phrase is `look up`
**When** the user types `Look up` or adds harmless whitespace/punctuation variation
**Then** the answer is accepted
**When** the user types `look in`
**Then** the answer is rejected with targeted particle-related feedback

### E2E-09 — Spelling contrast prefers confusables
**Given** a word with `word_confusables` entries
**And** word spelling is enabled
**When** a spelling contrast prompt is generated
**Then** distractors prefer current `word_confusables` data before synthetic misspellings

### E2E-10 — Confidence check is weak evidence only
**Given** a target reviewed via confidence-check mode
**When** the user selects the equivalent of “I recalled it”
**Then** the target receives only weak advancement compared with an objective correct answer
**And** if the user soon fails an objective check, analytics can identify this as false familiarity

### E2E-11 — Settings change behavior
**Given** review depth is `gentle` and audio spelling is disabled
**When** a session is generated
**Then** active sense cap is 1 and audio spelling prompts are absent by default
**When** review depth is changed to `deep` and audio spelling is enabled
**Then** active sense cap increases and typed/contextual/audio-spelling prompts become eligible
**And** settings persist across reloads/sessions

### E2E-12 — Existing manual override remains respected
**Given** a user completes a review and selects manual override `3d` or `never_for_now`
**When** the review is submitted
**Then** the stored next-due behavior matches the override rather than the automatic recommendation
**And** the event log clearly marks the manual override path

### E2E-13 — Backward compatibility with existing review data
**Given** existing review records created before the redesign
**When** the review system loads for a current user
**Then** the app continues to function without data loss
**And** old review records are either handled directly or migrated safely
**And** the redesign does not require destructive reset of existing review history

### E2E-14 — End-to-end frontend session
**Given** a due review queue exists
**When** the user opens the review screen, answers one card, views feedback, and proceeds to the next card
**Then** the full flow works end to end
**And** audio replay works when applicable
**And** feedback shows the correct supporting information
**And** subsequent card selection respects the backend scheduler and sibling-fatigue rules

---

## 19. Deliverables

At the end of the work, deliver:
1. updated plan doc in `docs/plans/`
2. any required ADR/docs updates
3. updated `docs/status/project-status.md` if repo workflow requires it
4. backend code changes
5. frontend code changes
6. migrations only if justified and limited to review-layer/settings changes
7. tests
8. rollout / hardening note

---

## 20. Definition of done

This work is done only when all of the following are true:
- the plan is written and repo-grounded
- the implementation follows the V1 constraints in this prompt
- meaning/phrase_sense targets work end to end
- multi-sense fatigue is controlled by progressive unlock + caps + sibling burying
- scheduler uses normalized grades and preserves manual overrides
- prompt building is sense-aware and ambiguity-safe
- advanced challenges work with proper validation/gating
- frontend settings and review UX function correctly
- analytics/event logging are coherent
- tests cover the critical behavior
- docs/status/plan updates are made according to repo rules
- final response/report clearly states what changed, what was verified, and what remains out of scope

---

## 21. What to do first in this Codex run

In this run, start by:
1. reading `AGENTS.md` and following it,
2. auditing the current review + lexicon + frontend files,
3. writing/updating the plan file,
4. listing the staged implementation tasks,
5. only then starting implementation.

If you find a conflict between this prompt and the repo, do not silently change direction. Document the conflict in the plan and explain the safest adaptation.
