# Voice Storage Policy Layer Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a policy layer between voice assets and storage roots so runtime can resolve audio through `policy -> primary_root (+ optional fallback_root)` instead of binding each asset directly to a specific root. This lets operators switch root targets for whole audio classes without reassigning every asset row.

**Performance note:** Runtime overhead is minimal if the API/playback paths eager-load or cache policy/root mappings. The steady-state cost is one extra join or one cached dict lookup per asset, which is negligible relative to I/O for DB fetches and audio file delivery.

**Architecture:** Replace direct `storage_root_id` on `lexicon_voice_assets` with a `storage_policy_id`. Add `lexicon_voice_storage_policies` with `policy_key`, `source_reference`, `content_scope`, `provider`, `family`, `locale`, `primary_storage_root_id`, and nullable `fallback_storage_root_id`. Import assigns assets to policies by dataset plus `scope + provider + family + locale`. Rewrite operations re-point the matching policies' primary and optional fallback roots without rewriting every asset row.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, lexicon CLI/import tools, Next.js admin frontend, pytest, Jest/RTL

---

### Task 1: Add failing expectations

**Files:**
- Modify: `backend/tests/test_lexicon_ops_api.py`
- Modify: `backend/tests/test_words.py`
- Modify: `admin-frontend/src/app/lexicon/voice/__tests__/page.test.tsx`

### Task 2: Add policy schema and migration

**Files:**
- Create: `backend/app/models/lexicon_voice_storage_policy.py`
- Modify: `backend/app/models/lexicon_voice_storage_root.py`
- Modify: `backend/app/models/lexicon_voice_asset.py`
- Create: `backend/alembic/versions/032_add_lexicon_voice_storage_policies.py`

### Task 3: Update import/rewrite/playback/admin APIs to use policies

**Files:**
- Modify: `tools/lexicon/voice_import_db.py`
- Modify: `backend/app/services/voice_assets.py`
- Modify: `backend/app/api/words.py`
- Modify: `backend/app/api/lexicon_ops.py`

### Task 4: Update admin UI to show roots and policies distinctly

**Files:**
- Modify: `admin-frontend/src/lib/lexicon-ops-client.ts`
- Modify: `admin-frontend/src/app/lexicon/voice/page.tsx`
- Modify: `admin-frontend/src/app/lexicon/voice/voice-storage-panel.tsx`

### Task 5: Verify and record evidence

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`
