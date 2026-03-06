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
| Auth + core vocabulary | PARTIAL | Register/login/refresh/me/logout, protected routes, lookup fallback | Register/login/me + search/detail done; refresh/logout/protected routes/dictionary fallback pending | `backend/app/api/auth.py`, `backend/app/api/words.py`, `frontend/src/app/login/page.tsx`, `frontend/src/app/register/page.tsx` | Complete auth lifecycle + protected-route enforcement |
| Word list + ePub import | PARTIAL | Word-list domain + import jobs + progress channel | Import skeleton and worker exist; full word-list domain and realtime progress path pending | `backend/app/api/imports.py`, `backend/app/tasks/epub_processing.py`, `backend/alembic/versions/003_add_epub_import.py` | Implement books/word_lists/word_list_items/import-jobs (+ progress stream) |
| Review + SM-2 queue | PARTIAL | Queue add/due/submit/stats + full integration | Queue API/service/frontend implemented; broader roadmap depth still pending | `backend/app/api/reviews.py`, `backend/app/services/review.py`, `frontend/src/app/review/page.tsx` | Close remaining roadmap gaps and harden flows |
| E2E + CI quality gates | DONE (baseline) | Required smoke gate on PR + broader suite | Smoke required on PR; full suite runs on main/dispatch | `.github/workflows/ci.yml`, `e2e/tests/smoke/*`, `e2e/tests/full/*` | Keep smoke minimal and non-flaky |
| Pre-prod readiness gate | DONE | Rollback drill + smoke + observability validation | Implemented and previously validated green | `.github/workflows/preprod-readiness.yml`, `docs/runbooks/preprod-readiness-checklist.md` | Keep green on release tags |
| Promotion automation wiring | DEFERRED | Real preprod deploy + prod promote via workflows | Workflows implemented; real infra command/URL wiring deferred to beta release | `.github/workflows/deploy-preprod.yml`, `.github/workflows/promote-prod.yml` | Wire real commands/URLs and run tagged dry-run |
| Concept learning (synsets, R/U/L) | PENDING | Phase 4 concepts/mastery system | Not started | `docs/plans/2026-02-26-full-rebuild.md` | Design + implement phase slice |
| AI/media/listening/stories/admin | PENDING | Phases 5-9 product expansion | Not started | `docs/plans/2026-02-26-full-rebuild.md` | Sequence after beta core readiness |

---

## Current Top Gaps (Priority Order)

1. Complete auth lifecycle and protected routes (`refresh`, `logout`, guard behavior, token lifecycle tests).
2. Build full word-list import domain (books/lists/items/jobs + realtime progress path).
3. Beta-release activation: wire real deploy/promote variables and pass full tagged promotion drill.

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
