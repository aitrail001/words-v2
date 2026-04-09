# Admin Lexicon Ops v1 Plan

**Goal:** Add a separate admin-only read-only operations UI for lexicon snapshot monitoring while the CLI remains the execution engine for build/enrich/validate/compile/import.

**Why now:** The lexicon pipeline is stable enough to benefit from operator visibility, especially for 1K+ staged rollouts with deferred ambiguous tails and resumable enrichment.

## Scope
- Separate admin frontend page for lexicon ops snapshot monitoring
- Admin-only backend API for listing snapshot runs and inspecting snapshot stage/file status
- No browser-triggered pipeline mutation in v1
- No replacement of CLI execution in v1

## Backend slice
- Add `backend/app/api/lexicon_ops.py`
- Add config for snapshots root in `backend/app/core/config.py`
- Register router in `backend/app/main.py`
- Add focused tests in `backend/tests/test_lexicon_ops_api.py`

### Endpoints
- `GET /api/lexicon-ops/snapshots`
  - list snapshot dirs under configured root
  - return file presence, counts, freshness, and coarse stage status
- `GET /api/lexicon-ops/snapshots/{snapshot_id}`
  - return per-file metrics and stage readiness summary

## Frontend slice
- Add `admin-frontend/src/app/lexicon/ops/page.tsx`
- Add `admin-frontend/src/lib/lexicon-ops-client.ts`
- Add focused page test
- Add minimal nav link from existing admin lexicon area

### UI sections
- snapshot list
- selected snapshot detail
- stage file checklist
- key counts: lexemes, senses, ambiguous tails, enrichments, checkpoints, failures, compiled rows
- warnings when stage artifacts are missing

## Non-goals
- trigger build/enrich/compile/import from browser
- artifact editing in UI
- filesystem upload/download management beyond links/metadata
- replacing existing review batch UI

## Verification
- backend API tests
- admin frontend tests
- lint/build for admin frontend
- targeted local smoke against a real snapshot directory
