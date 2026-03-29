# Voice Storage Root Normalization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Normalize voice storage configuration so `lexicon_voice_assets` no longer duplicate `storage_kind` and `storage_base` per row. Assets should keep only `relative_path` plus a reference to a shared storage root, allowing operators to repoint storage by updating one root record instead of rewriting every asset row.

**Architecture:** Add a new `lexicon_voice_storage_roots` table and make `lexicon_voice_assets.storage_root_id` the canonical storage link. Migrate existing rows into per-unique-root records, update playback resolution and admin storage APIs to operate on roots, and adapt the `/lexicon/voice` UI to show DB-backed storage roots/config rather than per-asset duplicated values.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, existing lexicon CLI/import tools, Next.js admin frontend, Jest/RTL, pytest

---

### Task 1: Add failing backend and frontend expectations

**Files:**
- Modify: `backend/tests/test_lexicon_ops_api.py`
- Modify: `backend/tests/test_words.py`
- Modify: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`

### Task 2: Implement normalized storage-root schema and migration

**Files:**
- Modify: `backend/app/models/lexicon_voice_asset.py`
- Create: `backend/app/models/lexicon_voice_storage_root.py`
- Create: `backend/alembic/versions/031_normalize_lexicon_voice_storage_roots.py`

### Task 3: Update import, rewrite, summary, and playback code to use roots

**Files:**
- Modify: `tools/lexicon/voice_import_db.py`
- Modify: `backend/app/services/voice_assets.py`
- Modify: `backend/app/api/words.py`
- Modify: `backend/app/api/lexicon_ops.py`

### Task 4: Update admin client/page wording and behavior

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts`
- Modify: `admin-frontend/src/app/lexicon/voice/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice/voice-storage-panel.tsx`

### Task 5: Verify and record evidence

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`
