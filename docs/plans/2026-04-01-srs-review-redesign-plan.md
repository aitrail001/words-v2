# SRS Review Redesign Implementation Plan

**Goal:** Bring the review redesign into compliance with `docs/prompts/2026-04-01_srs_review_ultimate_prompt.md` by shifting review state to true `meaning` / `phrase_sense` targets, tightening prompt selection and grading, improving feedback UX, and proving the behavior with backend, frontend, API, and E2E coverage.

**Non-goals:** No lexicon `sense_group` schema, no broad rewrite of unrelated lexicon pipelines, no new image-storage schema, and no production voice-capture implementation.

**Architecture:** Keep the existing review subsystem, but move review-state semantics from parent-entry-only tracking to target-level tracking while preserving parent entry display metadata. Add thin review-layer schema only where required for target identity and analytics, centralize prompt/grade selection in `ReviewService`, and keep the frontend contract incremental so existing flows keep working during migration.

**Staged implementation plan:**
1. Extend `entry_review_states` to track `target_type` / `target_id` while retaining parent `entry_type` / `entry_id`.
2. Rework due-queue generation around target-level state, progressive unlock, active caps, and sibling burying.
3. Rewrite prompt selection to be ambiguity-safe, stage-aware, phrase-aware, and media-aware.
4. Tighten grading and event logging around confidence, replay count, reveal usage, time buckets, and manual overrides.
5. Improve frontend feedback and settings behavior to match the backend contract.
6. Add or strengthen backend, API, frontend, and E2E tests against the prompt acceptance cases.

**Risks:**
- Backward compatibility with existing parent-scoped review rows.
- Query complexity when resolving parent/target state and bury rules.
- Frontend drift if new target-level metadata is added without consistent API typing.
- False confidence from unit coverage if isolated-stack E2E does not exercise the rewritten branch code.

**Acceptance criteria:**
- Review states are keyed by `meaning` / `phrase_sense` targets, not only parent words/phrases.
- Progressive unlock, preset caps, and sibling burying work at target level.
- Manual overrides still win over the automatic scheduler.
- Prompt building suppresses ambiguous bare prompts for multi-sense parents.
- Audio selection prefers example > sense > entry where data exists.
- Typed recall normalizes punctuation/whitespace/case and gives targeted phrasal-particle feedback.
- Confidence-only promotion remains weaker than objective success.
- Feedback UI shows the tested answer, sense definition, best example, and audio replay when available.
- Analytics can break down events by target type, parent type, input mode, replay count, time bucket, reveal usage, and confidence mismatch.
- Targeted backend, frontend, API, and isolated-stack E2E verification passes.

**Test strategy:**
- Backend unit/integration: `backend/tests/test_review_service.py`, `backend/tests/test_review_api.py`, `backend/tests/test_learner_knowledge_models.py`, `backend/tests/test_user_preferences_api.py`
- Frontend unit: `frontend/src/app/review/__tests__/page.test.tsx`, `frontend/src/app/settings/__tests__/page.test.tsx`, `frontend/src/lib/__tests__/user-preferences-client.test.ts`
- E2E smoke/integration: `e2e/tests/smoke/user-review-submit.smoke.spec.ts`, `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`, plus new prompt-aligned review smoke coverage added in this pass

**Current senior-review gap list:**
- `EntryReviewState` is still parent-entry scoped, which conflicts with the prompt’s V1 target model.
- Progressive unlock and coverage summary are currently derived from parent-level counters rather than target stability.
- Sibling burying is not enforced at target level.
- Prompt selection is only lightly ordered and still emits ambiguous prompt families for multi-sense parents.
- Audio prompt resolution does not currently prefer example/sense assets before entry assets.
- Typed answer validation only trims and lowercases; it does not normalize punctuation/whitespace robustly or explain phrasal-particle mistakes.
- Confidence and replay counts are logged but underused in grading and analytics.
- The review reveal flow sends the default schedule as a manual override, which mislabels event history.
- Feedback UI is still too thin for the prompt’s corrective-feedback requirements.
- Analytics summary does not yet expose the minimum breakdowns described in the prompt.

**Verification requirement before completion:** rerun fresh backend tests, frontend tests, `git diff --check`, and isolated-stack Playwright review flows after the rewrite.

**Future TODOs:**
- Real `speak_recall` microphone capture and transcription path. The current repo only supports typed fallback plus playback assets; do not treat prerecorded lexicon mp3s as user speech input.
- Broader live-corpus voice verification beyond the checked-in mini E2E fixtures. The current branch proves authenticated real-file playback with a tiny copied word/phrase sample; a later slice can expand that into larger corpus validation if needed.
