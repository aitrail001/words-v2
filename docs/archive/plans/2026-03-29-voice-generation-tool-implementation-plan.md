# Voice Generation Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an offline voice generation/import pipeline for reviewed lexicon rows, persist normalized voice metadata, and expose backend/admin inspection contracts without changing the learner frontend.

**Architecture:** Keep reviewed text and derived media separate. `voice-generate` projects from `approved.jsonl` into deterministic audio files plus JSONL ledgers, `voice-import-db` loads manifest rows into a normalized `lexicon_voice_assets` table, and backend/admin read surfaces expose flat voice asset metadata plus backend playback URLs.

**Tech Stack:** Python CLI tooling, Google Cloud Text-to-Speech client, SQLAlchemy/Alembic, FastAPI, Next.js admin frontend.

---

### Task 1: Write Voice Tool Docs

**Files:**
- Create: `docs/plans/2026-03-29-voice-generation-tool-design.md`
- Create: `docs/plans/2026-03-29-voice-generation-tool-implementation-plan.md`

**Step 1: Write the design doc**

Document:

- separate derived audio artifacts from `approved.jsonl`
- provider/family/voice defaults vs overrides
- locale and voice-role expansion
- DB schema and backend playback boundary

**Step 2: Write the implementation plan**

Document:

- exact files for CLI, DB, backend API, and admin changes
- expected tests to add or update
- verification commands

**Step 3: Commit**

```bash
git add docs/plans/2026-03-29-voice-generation-tool-design.md docs/plans/2026-03-29-voice-generation-tool-implementation-plan.md
git commit -m "docs: add voice generation design and implementation plan"
```

### Task 2: Add Offline Voice Generation Commands

**Files:**
- Create: `tools/lexicon/voice_generate.py`
- Create: `tools/lexicon/voice_import_db.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/requirements.txt`
- Test: `tools/lexicon/tests/test_cli.py`
- Test: `tools/lexicon/tests/test_voice_generate.py`

**Step 1: Write the failing tests**

Add tests that cover:

- `voice-generate` appearing in CLI help
- `voice-import-db` appearing in CLI help
- work-unit expansion from one approved row into both locales and both voice roles
- success/error ledger writing with a fake provider that fails one unit

**Step 2: Run targeted tests**

Run:

```bash
python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_voice_generate.py -q
```

Expected: failures for missing commands/modules.

**Step 3: Write the generation/import implementation**

Implement:

- deterministic work-unit expansion from compiled rows
- provider/family/voice/profile config defaults and override files
- bounded concurrent synthesis with append-only ledgers
- optional dry run planning
- manifest import into DB-ready metadata rows

**Step 4: Run targeted tests**

Run:

```bash
python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_voice_generate.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add tools/lexicon/voice_generate.py tools/lexicon/voice_import_db.py tools/lexicon/cli.py tools/lexicon/requirements.txt tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_voice_generate.py
git commit -m "feat(lexicon): add offline voice generation and import commands"
```

### Task 3: Add Normalized Voice Asset Storage

**Files:**
- Create: `backend/app/models/lexicon_voice_asset.py`
- Modify: `backend/app/models/word.py`
- Modify: `backend/app/models/meaning.py`
- Modify: `backend/app/models/meaning_example.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/030_add_lexicon_voice_assets.py`

**Step 1: Write the failing model/API expectations**

Use existing API tests as the first failing check after schema wiring lands in responses.

**Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py -q
```

Expected: failures because `voice_assets` model/fields are missing.

**Step 3: Write the schema**

Add:

- `lexicon.lexicon_voice_assets`
- one-of foreign key check across word/meaning/example
- relationships from parent models

**Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py -q
```

Expected: still failing until API surfaces are updated.

**Step 5: Commit**

```bash
git add backend/app/models/lexicon_voice_asset.py backend/app/models/word.py backend/app/models/meaning.py backend/app/models/meaning_example.py backend/app/models/__init__.py backend/alembic/versions/030_add_lexicon_voice_assets.py
git commit -m "feat(backend): add normalized lexicon voice asset storage"
```

### Task 4: Expose Backend Voice Read APIs

**Files:**
- Create: `backend/app/services/voice_assets.py`
- Modify: `backend/app/api/words.py`
- Modify: `backend/app/api/lexicon_inspector.py`
- Test: `backend/tests/test_words.py`
- Test: `backend/tests/test_lexicon_inspector_api.py`

**Step 1: Extend tests**

Add assertions for:

- `voice_assets` array on word enrichment detail
- `voice_assets` array on lexicon inspector word detail
- backend playback URL shape

**Step 2: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py -q
```

Expected: fail because response fields are missing.

**Step 3: Implement API/service updates**

Add:

- shared load/serialization helpers for voice assets
- backend playback endpoint that serves local files or redirects remote storage URLs
- flat `voice_assets` arrays on the existing word/admin detail responses

**Step 4: Run targeted tests**

Run:

```bash
PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/services/voice_assets.py backend/app/api/words.py backend/app/api/lexicon_inspector.py backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py
git commit -m "feat(api): expose lexicon voice asset metadata and playback urls"
```

### Task 5: Adapt Admin DB Inspector

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-inspector-client.ts`
- Modify: `admin-frontend/src/lib/words-client.ts`
- Modify: `admin-frontend/src/app/lexicon/db-inspector/page.tsx`

**Step 1: Add the failing UI expectations**

Add or update the page/unit tests so the inspector expects a voice asset count and per-asset rows.

**Step 2: Run targeted tests**

Run:

```bash
pnpm --dir admin-frontend test -- --runInBand db-inspector
```

Expected: fail because the UI/types do not know about voice assets.

**Step 3: Implement the UI adaptation**

Add:

- client types for voice assets
- inspector summary card for voice asset count
- per-asset list showing scope, locale, role, format, status, and playback URL

**Step 4: Run targeted tests**

Run:

```bash
pnpm --dir admin-frontend test -- --runInBand db-inspector
```

Expected: pass.

**Step 5: Commit**

```bash
git add admin-frontend/src/lib/lexicon-inspector-client.ts admin-frontend/src/lib/words-client.ts admin-frontend/src/app/lexicon/db-inspector/page.tsx
git commit -m "feat(admin): surface voice assets in lexicon db inspector"
```

### Task 6: Final Verification And Status Update

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run focused verification**

Run:

```bash
python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_voice_generate.py -q
PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_lexicon_inspector_api.py -q
python -m py_compile tools/lexicon/voice_generate.py tools/lexicon/voice_import_db.py backend/app/models/lexicon_voice_asset.py backend/app/services/voice_assets.py backend/app/api/words.py backend/app/api/lexicon_inspector.py
```

Expected: pass.

**Step 2: Update live status**

Add a concise entry to `docs/status/project-status.md` with:

- what shipped
- evidence commands and results
- any deferred follow-up, especially learner/review playback UI

**Step 3: Commit**

```bash
git add docs/status/project-status.md
git commit -m "docs(status): record voice generation backend/admin slice"
```
