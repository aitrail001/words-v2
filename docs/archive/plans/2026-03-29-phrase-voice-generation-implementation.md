# Phrase Voice Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the existing voice generation pipeline to support reviewed phrase datasets end to end and add enrich-style operator progress output to `voice-generate`.

**Architecture:** Keep one shared voice asset system. Add phrase ownership fields to `lexicon_voice_assets`, teach the generator/importer to plan and resolve phrase rows, expose phrase voice assets through existing backend/admin surfaces, and add structured progress logging to the CLI without changing the three-policy storage model.

**Tech Stack:** Python CLI tooling, SQLAlchemy/Alembic, FastAPI backend, Next.js admin frontend, pytest, Playwright/Jest where applicable.

---

### Task 1: Capture phrase planner behavior in failing CLI tests

**Files:**
- Modify: `tools/lexicon/tests/test_voice_generate.py`
- Test: `tools/lexicon/tests/test_voice_generate.py`

**Step 1: Write the failing test**

Add tests that assert `voice-generate` plans units for `entry_type: "phrase"` rows using:
- base phrase text as `content_scope=word`
- phrase sense definitions as `content_scope=definition`
- phrase sense examples as `content_scope=example`

Also add a failing test that asserts word and phrase rows can coexist in the same input.

**Step 2: Run test to verify it fails**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_generate.py -q`
Expected: FAIL because phrase rows are currently skipped.

**Step 3: Write minimal implementation**

Modify `tools/lexicon/voice_generate.py` planner helpers so phrase rows are accepted and expanded into work units.

**Step 4: Run test to verify it passes**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_generate.py -q`
Expected: PASS for the new phrase planner tests.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_voice_generate.py tools/lexicon/voice_generate.py
git commit -m "feat(lexicon): plan phrase voice generation"
```

### Task 2: Capture progress-output behavior in failing CLI tests

**Files:**
- Modify: `tools/lexicon/tests/test_voice_generate.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Test: `tools/lexicon/tests/test_voice_generate.py`

**Step 1: Write the failing test**

Add tests asserting that `voice-generate` prints:
- startup config
- planning summary
- live progress snapshots
- completion summary
- concise failure lines for failed units

Use stable string fragments, not brittle full-line snapshots.

**Step 2: Run test to verify it fails**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_generate.py tools/lexicon/tests/test_cli.py -q`
Expected: FAIL because current output is too sparse.

**Step 3: Write minimal implementation**

Modify `tools/lexicon/voice_generate.py` to emit structured operator progress with rate-limited snapshots and deterministic summary sections.

**Step 4: Run test to verify it passes**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_voice_generate.py tools/lexicon/tests/test_cli.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_voice_generate.py tools/lexicon/tests/test_cli.py tools/lexicon/voice_generate.py
git commit -m "feat(lexicon): add voice generation progress output"
```

### Task 3: Add phrase ownership to the voice asset model with failing backend tests first

**Files:**
- Modify: `backend/tests/test_models.py`
- Modify: `backend/app/models/lexicon_voice_asset.py`
- Create: `backend/alembic/versions/036_add_phrase_voice_asset_ownership.py`
- Possibly modify: `backend/app/models/phrase_entry.py`
- Possibly modify: `backend/app/models/phrase_sense.py`
- Possibly modify: `backend/app/models/phrase_sense_example.py`

**Step 1: Write the failing test**

Add model tests asserting `LexiconVoiceAsset` supports phrase-side ownership fields and ownership validation rules.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m pytest backend/tests/test_models.py -q`
Expected: FAIL because phrase ownership fields do not exist yet.

**Step 3: Write minimal implementation**

Add phrase foreign keys and relationships:
- `phrase_entry_id`
- `phrase_sense_id`
- `phrase_sense_example_id`

Add migration `036_add_phrase_voice_asset_ownership.py` and ownership validation constraints consistent with `content_scope`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m pytest backend/tests/test_models.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/test_models.py backend/app/models/lexicon_voice_asset.py backend/app/models/phrase_entry.py backend/app/models/phrase_sense.py backend/app/models/phrase_sense_example.py backend/alembic/versions/036_add_phrase_voice_asset_ownership.py
git commit -m "feat(backend): add phrase voice asset ownership"
```

### Task 4: Capture phrase DB import in failing lexicon tests

**Files:**
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_voice_generate.py`
- Modify: `tools/lexicon/voice_import_db.py`

**Step 1: Write the failing test**

Add tests asserting `voice-import-db` can import manifest rows for:
- phrase entry audio
- phrase sense definition audio
- phrase sense example audio

Use real phrase fixture rows shaped like reviewed phrase input.

**Step 2: Run test to verify it fails**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_generate.py -q`
Expected: FAIL because importer only resolves word-side entities.

**Step 3: Write minimal implementation**

Modify `tools/lexicon/voice_import_db.py` to resolve phrase-side owners and persist shared voice assets against phrase entities.

**Step 4: Run test to verify it passes**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_generate.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_voice_generate.py tools/lexicon/voice_import_db.py
git commit -m "feat(lexicon): import phrase voice assets"
```

### Task 5: Expose phrase voice assets in backend APIs with failing tests first

**Files:**
- Modify: `backend/tests/test_lexicon_inspector_api.py`
- Modify: `backend/tests/test_words.py`
- Modify: `backend/app/api/lexicon_inspector.py`
- Modify: `backend/app/services/voice_assets.py`
- Possibly modify: `backend/app/api/words.py`

**Step 1: Write the failing test**

Add backend tests asserting:
- phrase inspector detail includes phrase `voice_assets`
- playback resolution works for phrase-linked assets through the existing asset content route

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py backend/tests/test_words.py -q`
Expected: FAIL because phrase-linked assets are not surfaced yet.

**Step 3: Write minimal implementation**

Update backend loaders and serializers so phrase detail returns `voice_assets` in the same shape used for word detail, and asset playback keeps working through the existing route.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m pytest backend/tests/test_lexicon_inspector_api.py backend/tests/test_words.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/test_lexicon_inspector_api.py backend/tests/test_words.py backend/app/api/lexicon_inspector.py backend/app/services/voice_assets.py backend/app/api/words.py
git commit -m "feat(api): expose phrase voice assets"
```

### Task 6: Update admin UI where phrase voice data is visible

**Files:**
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx`
- Modify: `admin-frontend/src/lib/lexicon-inspector-client.ts`

**Step 1: Write the failing test**

Add frontend tests asserting phrase detail in DB Inspector can render returned `voice_assets` clearly.

**Step 2: Run test to verify it fails**

Run: `pnpm --dir admin-frontend test -- --runInBand db-inspector`
Expected: FAIL if phrase voice data is not rendered.

**Step 3: Write minimal implementation**

Update the inspector client types and rendering path so phrase voice assets display consistently with word voice assets.

**Step 4: Run test to verify it passes**

Run: `pnpm --dir admin-frontend test -- --runInBand db-inspector`
Expected: PASS.

**Step 5: Commit**

```bash
git add admin-frontend/src/app/lexicon/db-inspector/page.tsx admin-frontend/src/app/lexicon/db-inspector/__tests__/page.test.tsx admin-frontend/src/lib/lexicon-inspector-client.ts
git commit -m "feat(admin): show phrase voice assets"
```

### Task 7: Update docs and status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write the failing test**

No automated test. Use doc updates as acceptance criteria.

**Step 2: Run test to verify it fails**

Not applicable.

**Step 3: Write minimal implementation**

Document:
- phrase support in `voice-generate`
- progress output behavior
- phrase import path
- any operator command changes
- status evidence after verification

**Step 4: Run test to verify it passes**

Not applicable.

**Step 5: Commit**

```bash
git add tools/lexicon/README.md tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md
git commit -m "docs(lexicon): document phrase voice generation"
```

### Task 8: Full verification

**Files:**
- Verify changed files above

**Step 1: Run focused lexicon tests**

Run: `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
Expected: PASS.

**Step 2: Run backend tests**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m pytest backend/tests/test_models.py backend/tests/test_lexicon_inspector_api.py backend/tests/test_words.py -q`
Expected: PASS.

**Step 3: Run admin tests and lint**

Run: `pnpm --dir admin-frontend test -- --runInBand db-inspector`
Expected: PASS.

Run: `pnpm --dir admin-frontend exec eslint src/app/lexicon/db-inspector/page.tsx src/app/lexicon/db-inspector/__tests__/page.test.tsx src/lib/lexicon-inspector-client.ts --max-warnings=0`
Expected: PASS.

**Step 4: Run compile sanity**

Run: `PYTHONPATH=backend ./.venv-backend/bin/python -m py_compile backend/app/api/lexicon_inspector.py backend/app/api/words.py backend/app/models/lexicon_voice_asset.py backend/app/services/voice_assets.py tools/lexicon/voice_generate.py tools/lexicon/voice_import_db.py`
Expected: PASS.

**Step 5: Commit**

```bash
git add -A
git commit -m "test: verify phrase voice generation support"
```
