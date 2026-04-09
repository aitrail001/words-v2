# Learner Phrase Contract and Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize learner-serving phrase data, preserve phrase/example translations end-to-end, and make knowledge-map list/detail payloads consistent and lighter for words and phrases.

**Architecture:** Move learner-hot phrase fields off `phrase_entries.compiled_payload` into structured persistence, then update import, backend shaping, and frontend rendering to read one canonical contract. Keep provenance JSON only where it still has operator value, and keep range/list responses thinner than detail responses.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Postgres, Next.js/React, TypeScript, Python lexicon tooling, pytest/Jest

---

### Task 1: Add failing backend tests for canonical list/detail contract

**Files:**
- Modify: `backend/tests/test_knowledge_map_api.py`
- Inspect during implementation only if needed: `backend/app/api/knowledge_map.py`
- Inspect during implementation only if needed: `backend/app/services/knowledge_map.py`

**Step 1: Write the failing tests**

Add focused tests that assert:

- phrase-only ranges include both `primary_definition` and `translation` when both exist
- mixed ranges include both fields for phrase and word items with identical semantics
- phrase detail returns `null` localized fields instead of `"Translation unavailable"`
- phrase detail explicitly pins the current `compiled_payload`-backed behavior until the later normalization tasks replace that source

Prefer extending the existing knowledge-map fixtures instead of introducing a second fixture system.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: FAIL on the new phrase/list/detail assertions.

**Step 3: Write minimal implementation**

Update the backend response models and shaping logic so the failing assertions become valid targets, but do not add schema changes yet.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: PASS for the newly added contract assertions, with later tasks still pending.

**Step 5: Commit**

```bash
git add backend/tests/test_knowledge_map_api.py backend/app/api/knowledge_map.py backend/app/services/knowledge_map.py
git commit -m "test: pin canonical learner phrase contract"
```

### Task 2: Add failing importer tests for phrase example-translation preservation

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_translations_pipeline.py`
- Inspect during implementation only if needed: `tools/lexicon/import_db.py`

**Step 1: Write the failing tests**

Add tests that prove:

- phrase example translations present in approved/compiled rows survive import
- importer writes all learner-facing phrase examples needed by the app, not just top-level sense text
- missing required phrase/example translation fields fail explicitly rather than silently degrading

Use the smallest possible approved/compiled fixture rows inline in the tests.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

Expected: FAIL on the new phrase/example translation preservation assertions.

**Step 3: Write minimal implementation**

Adjust import/export handling in `tools/lexicon/import_db.py` so phrase localized definitions, example translations, and related learner-facing fields survive import intact.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

Expected: PASS for the new preservation tests.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py tools/lexicon/import_db.py
git commit -m "test: preserve phrase example translations on import"
```

### Task 3: Add structured phrase learner persistence

**Files:**
- Modify: `backend/app/models/phrase_entry.py`
- Create: `backend/alembic/versions/0xx_normalize_phrase_learner_fields.py`
- Modify: `backend/tests/test_models.py`
- Modify: `backend/tests/test_lexicon_phrase_reference_models.py`

**Step 1: Write the failing test**

Add model/migration-facing tests that pin the new structured phrase learner fields or related child tables needed for:

- ordered phrase senses
- localized definitions / usage notes by locale
- examples and example translations by locale
- per-sense learner metadata needed by phrase detail (`part_of_speech`, `register`, `primary_domain`, `secondary_domains`, `grammar_patterns`, `synonyms`, `antonyms`, `collocations`)

The tests must explicitly prove that a phrase payload carrying multiple supported locales survives normalization without dropping non-primary locales.

Keep the test focused on persistence shape, not API rendering.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_lexicon_phrase_reference_models.py -q`

Expected: FAIL because the normalized phrase learner schema does not exist yet.

**Step 3: Write minimal implementation**

Add the structured phrase learner persistence model and migration. Keep provenance compatibility with `compiled_payload`, but make the new structured fields authoritative for learner-serving reads.

The normalized phrase schema must be locale-aware. Do not collapse phrase localized fields down to a single chosen locale. Preserve all supported locales for:

- sense localized definition
- sense localized usage note
- example translation

The normalized phrase schema must also persist learner-visible phrase metadata per sense so later read paths do not rely on heuristic `compiled_payload` fallback matching.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_lexicon_phrase_reference_models.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/models/phrase_entry.py backend/alembic/versions/0xx_normalize_phrase_learner_fields.py backend/tests/test_models.py backend/tests/test_lexicon_phrase_reference_models.py
git commit -m "feat: normalize learner-facing phrase fields"
```

### Task 4: Update importer to populate normalized phrase learner data

**Files:**
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_translations_pipeline.py`

**Step 1: Write the failing test**

Add one focused test that proves imported phrase rows populate the new normalized learner fields and no longer require `compiled_payload` for learner-serving content.

That test must cover multi-locale phrase translations and example translations surviving import into the normalized storage.

It must also cover per-sense phrase metadata surviving import into normalized storage.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

Expected: FAIL because the importer still treats `compiled_payload` as the main phrase source.

**Step 3: Write minimal implementation**

Update `import_compiled_rows()` and any helper functions so phrase senses/examples/translations are written into the normalized storage introduced in Task 3. Preserve `compiled_payload` only as provenance.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add tools/lexicon/import_db.py tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py
git commit -m "feat: import normalized learner phrase data"
```

### Task 5: Switch knowledge-map backend reads to the canonical learner contract

**Files:**
- Modify: `backend/app/api/knowledge_map.py`
- Modify: `backend/app/services/knowledge_map.py`
- Modify: `backend/tests/test_knowledge_map_api.py`

**Step 1: Write the failing test**

Add one focused regression test asserting that range/list endpoints use a thin summary projection and that phrase detail is sourced from normalized learner data rather than repeated `compiled_payload` traversal.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: FAIL on the projection/canonical-source assertions.

**Step 3: Write minimal implementation**

Refactor the backend knowledge-map shaping functions to:

- share one summary contract for words and phrases
- return both English and localized text consistently
- reserve heavy sense/example hydration for detail endpoints
- remove synthetic `"Translation unavailable"` behavior from backend payload shaping
- read phrase detail metadata from normalized phrase-sense storage rather than `compiled_payload`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/api/knowledge_map.py backend/app/services/knowledge_map.py backend/tests/test_knowledge_map_api.py
git commit -m "feat: unify learner word and phrase read contract"
```

### Task 6: Add failing frontend tests for consistent bilingual rendering

**Files:**
- Modify: `frontend/src/components/knowledge-map-range-detail.tsx`
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Create or modify: `frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx`
- Create or modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
- Modify if needed: `frontend/src/lib/knowledge-map-client.ts`

**Step 1: Write the failing tests**

Add frontend tests asserting:

- list cards show English definition plus localized translation for words and phrases
- detail views render both fields consistently
- missing localized text does not render backend-originated `"Translation unavailable"` as if it were data

Keep tests on rendered behavior, not implementation details.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-map-range-detail.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: FAIL on current list/detail rendering.

**Step 3: Write minimal implementation**

Update the frontend client types and components to consume the unified backend contract and render the bilingual fields consistently with less entry-type-specific branching.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-map-range-detail.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/knowledge-map-range-detail.tsx frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx frontend/src/lib/knowledge-map-client.ts
git commit -m "test: pin bilingual learner rendering for words and phrases"
```

### Task 7: Reduce frontend render churn on entry detail and overlay navigation

**Files:**
- Modify: `frontend/src/components/knowledge-entry-detail-page.tsx`
- Modify: `frontend/src/components/knowledge-map-range-detail.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx`
- Modify: `frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx`

**Step 1: Write the failing test**

Add one focused test for the highest-value churn scenario you can reproduce cheaply, such as repeated overlay/detail state updates causing unnecessary recalculation for unchanged entry data.

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx src/components/__tests__/knowledge-map-range-detail.test.tsx`

Expected: FAIL on the targeted churn scenario.

**Step 3: Write minimal implementation**

Reduce state coupling and repeated derived work in the detail and range-detail components. Keep the change narrow: memoize only where it protects the hot render path.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-entry-detail-page.test.tsx src/components/__tests__/knowledge-map-range-detail.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/knowledge-entry-detail-page.tsx frontend/src/components/knowledge-map-range-detail.tsx frontend/src/components/__tests__/knowledge-entry-detail-page.test.tsx frontend/src/components/__tests__/knowledge-map-range-detail.test.tsx
git commit -m "perf: reduce learner detail render churn"
```

### Task 8: Update project status with verification evidence

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Write the status update**

Add a concise entry that records:

- canonical learner word/phrase contract cleanup
- normalized phrase learner storage
- phrase example translation preservation
- exact verification commands and results

**Step 2: Verify the status change is accurate**

Run only the verification commands already executed in prior tasks. Do not invent new evidence.

Expected: the status entry references fresh results from completed tasks.

**Step 3: Commit**

```bash
git add docs/status/project-status.md
git commit -m "docs: record learner phrase contract hardening status"
```

### Task 9: Run the scoped verification bundle

**Files:**
- No code changes expected

**Step 1: Run backend knowledge-map verification**

Run: `PYTHONPATH=backend /Users/johnson/AI/src/words-v2/.venv-backend/bin/python -m pytest backend/tests/test_knowledge_map_api.py backend/tests/test_models.py backend/tests/test_lexicon_phrase_reference_models.py -q`

Expected: PASS.

**Step 2: Run lexicon importer verification**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_translations_pipeline.py -q`

Expected: PASS.

**Step 3: Run frontend verification**

Run: `cd frontend && npm test -- --runInBand src/components/__tests__/knowledge-map-range-detail.test.tsx src/components/__tests__/knowledge-entry-detail-page.test.tsx`

Expected: PASS.

**Step 4: Commit**

```bash
git commit --allow-empty -m "chore: record learner phrase contract verification checkpoint"
```
