# Project Status Board (Source of Truth)

**Status:** ACTIVE  
**Last Updated (UTC):** 2026-03-06  
**Owner:** Engineering  
**Scope:** Live delivery status for features, quality gates, and release readiness.

---

## Rules of Use

1. This file is the only live status source of truth.
2. Any status change must include fresh evidence in this file (tests, workflow run, or commit/PR).
3. Update this board in the same PR/commit as the implementation change whenever possible.
4. If no status changed, add a short timestamped "No Change" entry in `Status Change Log`.
5. Keep detailed implementation narratives in `docs/plans/*`; keep this board concise and evidence-linked.

---

## Consolidated Source Inputs

This board consolidates progress from:

- `docs/plans/2026-02-26-full-rebuild.md` (target scope roadmap)
- `docs/plans/2026-03-05-current-state-phase-plan.md` (evidence-based implementation state)
- `docs/runbooks/preprod-readiness-checklist.md` (operational pre-prod gate)
- `docs/runbooks/release-promotion.md` (promotion sequence and commands)
- `docs/runbooks/rollback.md` (rollback procedure)
- `.github/workflows/ci.yml`, `.github/workflows/preprod-readiness.yml`, `.github/workflows/deploy-preprod.yml`, `.github/workflows/promote-prod.yml` (delivery gates)

---

## Workstream Matrix

| Workstream | Status | Target Scope | Current Reality | Evidence | Next Milestone |
|---|---|---|---|---|---|
| Foundation platform | DONE | Docker stack, health checks, CI baseline | In place and stable | `docker-compose.yml`, `.github/workflows/ci.yml`, `backend/app/api/health.py` | Maintain |
| Auth + core vocabulary | PARTIAL | Register/login/refresh/me/logout, protected routes, lookup fallback | Register/login/me/refresh/logout implemented with refresh rotation + access-token revocation; frontend protected routes + logout UX + 401 lifecycle handling are in place; dictionary lookup fallback still pending | `backend/app/api/auth.py`, `backend/app/services/auth_tokens.py`, `frontend/src/lib/api-client.ts`, `frontend/src/middleware.ts`, `e2e/tests/smoke/auth-contract.smoke.spec.ts`, `e2e/tests/smoke/auth-guard.smoke.spec.ts` | Implement dictionary API fallback for `/api/words/lookup` misses and add coverage |
| Word list + ePub import | DONE | Word-list domain + import jobs + progress channel | Import pipeline hardened for real runtime: worker no longer hard-fails when `en_core_web_sm` is missing (fallback NLP path), backend/worker now share upload storage path, and full E2E now asserts terminal `completed` status with a valid EPUB fixture | `backend/app/tasks/epub_processing.py`, `backend/app/core/uploads.py`, `backend/app/api/word_lists.py`, `backend/app/api/imports.py`, `backend/tests/test_epub_processing.py`, `e2e/tests/full/import-terminal.full.spec.ts`, `e2e/tests/helpers/import-jobs.ts`, `e2e/tests/fixtures/epub/valid-minimal.epub` | Add object-storage upload path + temp-resource lifecycle cleanup (success/failure/TTL) with automated coverage |
| Review + SM-2 queue | PARTIAL | Queue add/due/submit/stats + full integration | Queue API/service/frontend implemented; broader roadmap depth still pending | `backend/app/api/reviews.py`, `backend/app/services/review.py`, `frontend/src/app/review/page.tsx` | Close remaining roadmap gaps and harden flows |
| E2E + CI quality gates | DONE (baseline) | Required smoke gate on PR + broader suite | Smoke required on PR; auth contract + protected-route smoke coverage added; full suite runs on main/dispatch | `.github/workflows/ci.yml`, `e2e/tests/smoke/*`, `e2e/tests/full/*` | Keep smoke minimal and non-flaky |
| Pre-prod readiness gate | DONE | Rollback drill + smoke + observability validation | Implemented and previously validated green | `.github/workflows/preprod-readiness.yml`, `docs/runbooks/preprod-readiness-checklist.md` | Keep green on release tags |
| Promotion automation wiring | DEFERRED | Real preprod deploy + prod promote via workflows | Workflows implemented; real infra command/URL wiring deferred to beta release | `.github/workflows/deploy-preprod.yml`, `.github/workflows/promote-prod.yml` | Wire real commands/URLs and run tagged dry-run |
| Concept learning (synsets, R/U/L) | PENDING | Phase 4 concepts/mastery system | Not started | `docs/plans/2026-02-26-full-rebuild.md` | Design + implement phase slice |
| AI/media/listening/stories/admin | PENDING | Phases 5-9 product expansion | Not started | `docs/plans/2026-02-26-full-rebuild.md` | Sequence after beta core readiness |

---

## Current Top Gaps (Priority Order)

1. Implement dictionary API fallback for `/api/words/lookup` misses + tests.
2. Move import source storage from local/container temp paths to object storage (or equivalent shared ephemeral layer) with guaranteed cleanup on completion/failure and periodic TTL cleanup.
3. Beta-release activation: wire real deploy/promote variables and pass full tagged promotion drill.
4. Concept learning (synsets, R/U/L) phase design and first implementation slice.

---

## Release Readiness Snapshot

| Gate | Required | Current | Evidence |
|---|---|---|---|
| Backend lint + tests | Yes | Green | `CI / Backend (lint + test)` |
| Frontend lint + tests | Yes | Green | `CI / Frontend (lint + test)` |
| E2E smoke on PR | Yes | Green | `CI / E2E Smoke (required)` |
| Preprod readiness workflow | Yes (for release) | Available | `.github/workflows/preprod-readiness.yml` |
| Deploy preprod workflow | Yes (for release) | Available (placeholder vars) | `.github/workflows/deploy-preprod.yml` |
| Production promote workflow | Yes (for release) | Available (placeholder vars) | `.github/workflows/promote-prod.yml` |
| Rollback runbook | Yes | Ready | `docs/runbooks/rollback.md` |

---

## Required Update Checklist (Every Significant Change)

1. Update relevant workstream row(s) in this board.
2. Add or refresh evidence link(s) (test command, workflow run, PR/commit).
3. Re-check release-readiness table if CI/workflows/runbooks changed.
4. Append one line in `Status Change Log`.

Suggested verification commands before marking a row as improved:

```bash
# Backend
cd backend && pytest -q

# Frontend
cd ../frontend && npm run lint && npm test -- --runInBand --watch=false

# CI workflow syntax (local sanity)
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "ci.yml OK"'
```

---

## Status Change Log

| Date (UTC) | Change | Editor | Evidence |
|---|---|---|---|
| 2026-03-06 | Initialized canonical project status board and consolidated tracking sources. | Codex | `docs/plans/2026-02-26-full-rebuild.md`, `docs/plans/2026-03-05-current-state-phase-plan.md` |
| 2026-03-06 | Auth lifecycle hardening implemented (backend refresh/logout with token lifecycle controls, frontend protected routes/logout/401-refresh behavior, auth smoke coverage). | Codex | `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` (113 passed), `npm --prefix frontend run lint` (pass), `npm --prefix frontend test -- --runInBand` (7 suites/26 tests passed), `docker compose -f docker-compose.yml --profile tests exec -T playwright ... npm run test:smoke:ci` (6 passed), `docker compose -f docker-compose.yml --profile tests exec -T playwright ... npm run test:full` (7 passed) |
| 2026-03-06 | Word-list import domain delivered: new domain tables/models/APIs/tasks + `/imports` frontend + import-domain smoke/full verification. | Codex | `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` (127 passed), `npm --prefix frontend run lint` (pass), `npm --prefix frontend test -- --runInBand` (9 suites/35 tests passed), `docker compose -f docker-compose.yml --profile tests exec -T backend alembic upgrade head` (to 005), `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:smoke:ci"` (7 passed), `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:full"` (8 passed) |
| 2026-03-06 | Import completion hardening delivered: fallback NLP for missing spaCy model, shared upload directory for backend/worker, and terminal-state full E2E with valid EPUB fixture. | Codex | `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest tests/test_epub_processing.py tests/test_word_lists_api.py tests/test_imports_api.py -q"` (17 passed), `docker compose -f docker-compose.test.yml run --rm --build test sh -lc "pip install -q -r requirements-test.txt && pytest -q"` (129 passed), `npm --prefix frontend run lint` (pass), `npm --prefix frontend test -- --runInBand` (9 suites/35 tests passed), `docker compose -f docker-compose.yml --profile tests exec -T backend alembic upgrade head` (to 005), `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:smoke:ci"` (7 passed), `docker compose -f docker-compose.yml --profile tests exec -T playwright sh -lc "cd /workspace/e2e && npm run test:full"` (9 passed) |
| 2026-03-06 | Added explicit TODO for import storage lifecycle: move upload/temp artifacts to object storage (or equivalent shared temp layer) and enforce cleanup guarantees. | Codex | `docs/status/project-status.md` |
