
# words-v2 agent guide

## Scope and precedence
- This is the canonical shared repo instruction file.
- More specific `AGENTS.md` files in subdirectories override this file for local work.
- `CLAUDE.md` exists only to import this file for Claude Code.

## Runtime Contract (Mac-first dual-stack)

Default local development on the Mac:
- start postgres and redis with `make infra-up`
- run backend, frontend, and admin-frontend as host processes
- run local Playwright with `e2e/playwright.local.config.ts`
- use database `vocabapp_dev_full`

Default persistent test stack (Mac now, NUC later):
- use `compose.infra.yml + compose.teststack.yml (+ compose.e2e.yml)` only
- run a full containerized stack with persistent DB `vocabapp_test_full`
- mount `${WORDS_DATA_DIR}` read-only into backend/worker/migrate
- use external Docker volumes `words_pg_data`, `words_redis_data`, and `words_uploads_data`

Do not do these unless the user explicitly asks:
- do not use `docker-compose.browser-proof.yml`
- do not mix host backend with container frontend/admin or container Playwright with host backend
- do not use repo-local `./data` as the canonical dataset location
- do not run `docker compose down -v` on the shared stack
- do not create alternate runtime shapes when the sanctioned files already cover the use case

Canonical commands:
- `make infra-up`
- `make local-backend-dev`
- `make local-frontend-dev`
- `make local-admin-dev`
- `make test-backend`
- `make test-frontend`
- `make test-admin`
- `make smoke-local`
- `make stack-build`
- `make stack-smoke`
- `make stack-full`
- `make db-bootstrap`
- `make db-refresh-template`


## Repo map
- `backend/` FastAPI backend
- `frontend/` learner app
- `admin-frontend/` admin app
- `e2e/` Playwright tests
- `tools/lexicon/` specialized offline/admin tooling

## Current truth
- Live status: `docs/status/project-status.md`
- Active runbooks: `docs/runbooks/`
- ADRs: `docs/decisions/`
- Detailed proof: `docs/reports/`
- Historical material under `docs/archive/` is not current truth
- Current lexicon operator contract: `tools/lexicon/README.md`

## How to work here
- Prefer the smallest safe change.
- For complex/risky/cross-slice work, use your planning workflow before coding.
- Prefer `gh` for GitHub operations; use `gh api` when no first-class command exists.
- Use subdirectory instructions if present.

## Verification
- Run the smallest relevant tests/lint/build for the changed slice.
- Report exactly what ran and what did not run.
- Do not claim completion without fresh verification.

## Docs updates
- Update runbooks/docs only when behavior/contracts/operator flow changed.
- Put long proof in `docs/reports/` or PRs, not in the status board.
- Update ADRs only for durable decisions.
- Keep current-truth docs short.
- Historical design/prototype material belongs under docs/archive/.
- Root repo instructions must not duplicate workflow detail already provided by external skills.
- When a document stops describing current behavior, either update it in the same change or archive it.

