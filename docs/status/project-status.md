# Project Status Board (Source of Truth)

**Status:** ACTIVE  
**Last Updated (UTC):** 2026-03-07  
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
| 2026-03-07 | Lexicon tool foundation implemented in worktree: Python CLI scaffold, WordNet/wordfreq base builder, validation/compiler modules, stable ID helpers, local DB importer foundation, and provenance-ready model/migration changes. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (27 tests passed), `python3 -m unittest tools.lexicon.tests.test_import_db` (2 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/import_db.py tools/lexicon/cli.py tools/lexicon/build_base.py tools/lexicon/compile_export.py tools/lexicon/validate.py backend/app/models/word.py backend/app/models/meaning.py backend/alembic/versions/006_add_lexicon_import_provenance.py` (pass); backend runtime model import smoke blocked locally because `sqlalchemy` is not installed in this shell. |
| 2026-03-07 | Lexicon tool snapshot file-I/O + CLI wiring delivered: normalized snapshot write support, snapshot validation from disk, compiled export generation, and `import-db --dry-run` CLI summary path. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (31 tests passed), `python3 -m unittest tools.lexicon.tests.test_cli` (5 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/jsonl_io.py tools/lexicon/build_base.py tools/lexicon/validate.py tools/lexicon/compile_export.py tools/lexicon/cli.py tools/lexicon/import_db.py` (pass) |
| 2026-03-07 | Lexicon tool admin import path hardened: real sync-session DB import wiring now mirrors backend patterns, CLI docs/tests reflect `--compiled-input`/`--compiled-path` and `--language`, and provenance columns are ready for compiled snapshot loads. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (35 tests passed), `python3 -m unittest tools.lexicon.tests.test_cli` (9 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/import_db.py tools/lexicon/cli.py tools/lexicon/build_base.py tools/lexicon/compile_export.py tools/lexicon/validate.py backend/app/models/word.py backend/app/models/meaning.py backend/alembic/versions/006_add_lexicon_import_provenance.py` (pass); real DB-path smoke still depends on local backend DB deps/settings. |
| 2026-03-07 | Lexicon provider/enrichment slice landed: `build-base` now resolves real WordNet + `wordfreq` providers with fail-loud dependency errors on the operator path, and a separate offline `enrich` command now writes `enrichments.jsonl` before validation/compile/import. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (40 tests passed), `python3 -m unittest tools.lexicon.tests.test_cli tools.lexicon.tests.test_enrich` (13 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/build_base.py tools/lexicon/wordnet_provider.py tools/lexicon/wordfreq_provider.py tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/import_db.py backend/app/models/word.py backend/app/models/meaning.py backend/alembic/versions/006_add_lexicon_import_provenance.py` (pass); live operator smoke with installed `nltk`/WordNet and `wordfreq` is not run in this shell because those packages/corpora are absent locally. |
| 2026-03-07 | Lexicon operator smoke verified in a repo-local venv: installed `tools/lexicon/requirements.txt`, downloaded WordNet corpora, and ran `build-base -> enrich -> validate -> compile-export` successfully against a real snapshot directory. | Codex | `./.venv-lexicon/bin/python -m pip install -r tools/lexicon/requirements.txt` (pass), `./.venv-lexicon/bin/python -m nltk.downloader wordnet omw-1.4` (pass), `./.venv-lexicon/bin/python -m tools.lexicon.cli build-base run set lead --output-dir /tmp/lexicon-smoke` (3 lexemes / 12 senses / 12 concepts), `./.venv-lexicon/bin/python -m tools.lexicon.cli enrich --snapshot-dir /tmp/lexicon-smoke` (12 enrichments), `./.venv-lexicon/bin/python -m tools.lexicon.cli validate --snapshot-dir /tmp/lexicon-smoke` (0 errors), `./.venv-lexicon/bin/python -m tools.lexicon.cli compile-export --snapshot-dir /tmp/lexicon-smoke --output /tmp/lexicon-smoke/words.enriched.jsonl` (3 compiled rows), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (40 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/build_base.py tools/lexicon/wordnet_provider.py tools/lexicon/wordfreq_provider.py tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/import_db.py backend/app/models/word.py backend/app/models/meaning.py backend/alembic/versions/006_add_lexicon_import_provenance.py` (pass). |
| 2026-03-07 | Added dedicated lexicon CI coverage: a new workflow job now installs tool-local deps, caches/downloads WordNet corpora, runs `tools/lexicon` unit tests, and exercises the offline `build-base -> enrich -> validate -> compile-export` smoke flow without requiring a real LLM key. | Codex | `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "ci.yml OK"'` (pass), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (40 tests passed), local repo-local-venv smoke flow (pass). |
| 2026-03-07 | Added a separate manual/nightly lexicon OpenAI-compatible smoke workflow: it validates secret-backed endpoint config in a protected environment, installs tool-local deps, downloads WordNet corpora, and runs a bounded offline smoke flow without exposing the real LLM key in PR CI. | Codex | `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/lexicon-openai-compatible-smoke.yml"); puts "lexicon-openai-compatible-smoke.yml OK"'` (pass), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (40 tests passed). |
| 2026-03-07 | Real endpoint-backed lexicon enrichment landed: `enrich` now supports `auto|placeholder|openai_compatible` provider modes, `LEXICON_LLM_BASE_URL` config for OpenAI-compatible Responses endpoints, backward-compatible fallback from `LEXICON_LLM_PROVIDER`, and a manual/nightly workflow that exercises the real endpoint path while PR CI stays explicit placeholder-only. | Codex | `python3 -m unittest tools.lexicon.tests.test_enrich tools.lexicon.tests.test_config tools.lexicon.tests.test_cli` (22 tests passed), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (47 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/config.py tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/build_base.py tools/lexicon/wordnet_provider.py tools/lexicon/wordfreq_provider.py tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/import_db.py` (pass), `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); YAML.load_file(".github/workflows/lexicon-openai-compatible-smoke.yml"); puts "workflow yaml OK"'` (pass). |
| 2026-03-07 | Added a tiny local real-endpoint smoke command: `smoke-openai-compatible` now runs `build-base -> enrich(openai_compatible) -> validate -> compile-export` for a tiny seed set, and was verified end-to-end against a local OpenAI-compatible mock endpoint. | Codex | `python3 -m unittest tools.lexicon.tests.test_cli tools.lexicon.tests.test_enrich tools.lexicon.tests.test_config` (24 tests passed), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (49 tests passed), `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/config.py tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/build_base.py tools/lexicon/wordnet_provider.py tools/lexicon/wordfreq_provider.py tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/import_db.py` (pass), local mock smoke for `python -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-openai-compatible-local-smoke run set` (2 compiled rows, pass). |
| 2026-03-07 | OpenAI-compatible lexicon enrichment now validates required learner-facing response fields before record creation, failing loudly with field-specific errors for malformed `definition`, `examples`, or `confidence` payloads instead of silently falling back. | Codex | `python3 -m unittest tools.lexicon.tests.test_enrich` (9 tests passed), `python3 -m unittest tools.lexicon.tests.test_cli tools.lexicon.tests.test_enrich tools.lexicon.tests.test_config` (27 tests passed), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (52 tests passed), `PYTHONPYCACHEPREFIX=/tmp/lexicon-pycache python3 -m py_compile tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/config.py` (pass). |
| 2026-03-07 | OpenAI-compatible lexicon enrichment P1 schema hardening landed: the real provider path now validates CEFR/register enums, list-of-strings fields, `forms` shape, and `confusable_words` item structure before record creation, surfacing field-specific payload errors instead of silent coercion. | Codex | `python3 -m unittest tools.lexicon.tests.test_enrich` (14 tests passed), `python3 -m unittest tools.lexicon.tests.test_cli tools.lexicon.tests.test_enrich tools.lexicon.tests.test_config` (32 tests passed), `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (57 tests passed), `PYTHONPYCACHEPREFIX=/tmp/lexicon-pycache python3 -m py_compile tools/lexicon/enrich.py tools/lexicon/cli.py tools/lexicon/config.py` (pass). |
| 2026-03-07 | Added lexicon pytest support for local admin/dev use and CI: a dedicated dev requirements file now installs pytest into the repo-local lexicon venv, both lexicon workflows run `python -m pytest tools/lexicon/tests -q`, and the existing bounded smoke flow remains in place after tests. | Codex | `PIP_NO_CACHE_DIR=1 ./.venv-lexicon/bin/python -m pip install -r tools/lexicon/requirements-dev.txt` (pass), `./.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q` (57 passed), repo-local venv smoke flow for `build-base -> enrich --provider-mode placeholder -> validate -> compile-export` (3 lexemes / 12 enrichments / 3 compiled rows, pass), `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); YAML.load_file(".github/workflows/lexicon-openai-compatible-smoke.yml"); puts "workflow yaml OK"'` (pass). |
| 2026-03-07 | Real local DB import smoke verified for the lexicon tool against an isolated temporary Postgres instance: the worktree migration chain applied cleanly, a compiled export imported successfully, a second import updated in place without duplicate rows, and persisted provenance fields matched the expected `source_type` / `source_reference` values. | Codex | isolated DB smoke on alternate local ports with `alembic upgrade head` (001 -> 006 applied), `python -m tools.lexicon.cli import-db --input /tmp/lexicon-db-import-smoke/words.enriched.jsonl --source-type lexicon_snapshot --source-reference lexicon-smoke-20260307 --language en` (first run: 2 words / 4 meanings created), second identical import (2 words / 4 meanings updated), direct DB inspection confirmed 2 `words` rows and 4 `meanings` rows with `lexicon_snapshot` provenance. |
| 2026-03-07 | Added a Node-backed OpenAI-compatible lexicon transport for Cloudflare-fronted custom gateways: `openai_compatible_node` now uses the official Node OpenAI SDK, `LEXICON_LLM_TRANSPORT=node` can auto-select it, the manual/nightly smoke workflow installs tool-local Node deps when needed, and a real smoke against `https://api.nwai.cc` compiled 2 words successfully without changing the offline/admin pipeline shape. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (63 tests passed), `npm --prefix tools/lexicon ci` (pass), `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); YAML.load_file(".github/workflows/lexicon-openai-compatible-smoke.yml"); puts "workflow yaml OK"'` (pass), real smoke via `/tmp/lexicon-db-smoke-venv/bin/python -m tools.lexicon.cli smoke-openai-compatible --provider-mode openai_compatible_node --output-dir /tmp/lexicon-openai-node-smoke run set` with `LEXICON_LLM_BASE_URL=https://api.nwai.cc`, `LEXICON_LLM_MODEL=gpt-5.1`, and env-provided key (lexeme_count 2 / compiled_count 2, pass). |
| 2026-03-07 | Added operator-facing lexicon setup docs: a tool-local `tools/lexicon/.env.example` now shows safe offline/admin env configuration, `tools/lexicon/OPERATOR_GUIDE.md` documents setup and the full `build-base -> enrich -> validate -> compile-export -> import-db` flow, and the root `.env.example` now points operators to those tool-local references instead of duplicating the full admin configuration. | Codex | `python3 -m unittest discover -s tools/lexicon/tests -p "test_*.py"` (63 tests passed), `git diff --check` (pass). |
