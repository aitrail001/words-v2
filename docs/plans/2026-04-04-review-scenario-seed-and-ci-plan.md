# Review Scenario Seed And CI Plan

Goal: seed deterministic live review scenarios into the real learner queue for manual testing and drive the same scenarios through automated backend/e2e coverage and CI.

Architecture: add one reusable review-scenario fixture layer that inserts lexicon entries, learner state, preferences, and review states directly into the dev/test database. Use that layer from a manual seed command and from Playwright so the real backend generates prompt families instead of mocked route payloads.

Tech Stack: Python backend service/tests, PostgreSQL, Playwright, Node `pg`, Docker Compose, GitHub Actions CI.

## Scope

- Seed enough word/phrase data to exercise:
  - `sentence_gap`
  - `collocation_check`
  - `situation_matching`
  - `typed_recall`
  - `speak_recall`
  - `definition_to_entry`
  - `entry_to_definition`
  - `audio_to_definition`
- Make the seeded queue visible to existing local users for manual testing.
- Replace the mocked prompt-family smoke with a DB-backed smoke.
- Add/adjust backend regression coverage for deterministic prompt-family generation where useful.
- Keep CI running the DB-backed review smoke.

## Files To Touch

- Create: `scripts/seed_review_scenarios.py`
- Create: `e2e/tests/helpers/review-scenario-fixture.ts`
- Modify: `e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts`
- Modify: `e2e/tests/helpers/review-seed.ts`
- Modify: `backend/tests/test_review_service.py`
- Modify: `.github/workflows/ci.yml` only if CI wiring needs adjustment
- Modify: `docs/status/project-status.md`

## Implementation Steps

1. Add a failing backend regression test that asserts a seeded set of due review states can produce the target prompt families with real prompt-builder logic.
2. Add a failing Playwright smoke rewrite plan by converting the existing mocked prompt-family spec into a DB-backed flow that expects real prompt types in sequence.
3. Implement a reusable scenario fixture helper for e2e that seeds:
   - words, meanings, phrase entries, phrase senses
   - learner catalog entries
   - optional voice policy/assets for audio scenarios
   - user preferences needed for typed/speech/audio prompt availability
   - `learner_entry_statuses`
   - due `entry_review_states` ordered to force target prompt families
4. Implement `scripts/seed_review_scenarios.py` for local manual seeding against existing users, defaulting to all non-admin users unless an email filter is provided.
5. Update the Playwright prompt-family smoke to use the real fixture helper instead of route mocks and verify the actual review flow behavior for each scenario.
6. Run targeted backend tests, frontend lint if touched, Playwright review smoke, and the local seed script against the current stack.
7. Update `docs/status/project-status.md` with fresh evidence and the new manual seed command.
