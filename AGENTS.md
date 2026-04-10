
# words-v2 agent guide

## Scope and precedence
- This is the canonical shared repo instruction file.
- More specific `AGENTS.md` files in subdirectories override this file for local work.
- `CLAUDE.md` exists only to import this file for Claude Code.

## Runtime Contract (Mac-first dual-stack)

### Local dev on the Mac
Use host processes for daily development.
- start postgres and redis with `make infra-up`
- run backend, frontend, and admin-frontend as host processes
- worker runs locally when async features are being developed
- do not run worker in Docker while app services are local
- run local Playwright with `e2e/playwright.local.config.ts`
- Playwright local smoke runs locally
- Docker is used only for postgres, redis, and optional tools
- use database `vocabapp_dev_full`

Default persistent test stack (Mac now, NUC later):
- use `compose.infra.yml + compose.teststack.yml (+ compose.e2e.yml)` only
- run a full containerized stack with persistent DB `vocabapp_test_full`
- mount `${WORDS_DATA_DIR}` read-only into backend/worker/migrate
- use external Docker volumes `words_pg_data`, `words_redis_data`, `words_uploads_data`, `words_pgadmin_data`, and `words_redis_commander_data`

Do not do these unless the user explicitly asks:
- do not mix host backend with container frontend/admin or container Playwright with host backend
- do not run `docker compose down -v` on the shared stack
- do not create alternate runtime shapes when the sanctioned files already cover the use case

Canonical commands:
- `make worktree-bootstrap`
- `make infra-up`
- `make local-backend-dev`
- `make local-worker-dev`
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

### Worktree bootstrap

Every new worktree must run:
```bash
    make worktree-bootstrap
```

Rules:
- Never create a fresh backend venv inside each worktree if a shared hashed venv can be reused.
- Use the repo-root symlink .venv-backend that points to the shared backend venv under ~/.cache/words/venvs/...
- Keep node_modules local to each worktree.
- Reuse shared npm cache under ~/.cache/words/npm
- Reuse shared Playwright browser cache under ~/.cache/words/ms-playwright

## Repo map
- `backend/` FastAPI backend
- `frontend/` learner app
- `admin-frontend/` admin app
- `e2e/` Playwright tests
- `tools/lexicon/` specialized offline/admin tooling
- `docs/archive/` Historical material under is not current truth


## How to work here
Prefer the smallest safe change that solves the requested problem.

Use external workflow skills or personal tooling when helpful, but do not restate those workflow details here. This file gives repo-specific constraints, not a full engineering methodology.

For planning:
- tiny change: no written plan required
- normal change: optional brief plan
- risky or cross-slice change: use your preferred planning workflow before coding

Treat these as risky or cross-slice by default:
- schema or migration changes
- auth / permissions / secrets handling
- review or SRS behavior changes
- import pipeline changes
- CI / release workflow changes
- lexicon artifact-contract changes
- anything touching more than one app plus backend

## Git and GitHub

- Keep branches and commits focused.
- Do not mix unrelated cleanup into a feature change.
- Avoid destructive git commands unless explicitly requested.
- Prefer `gh` for GitHub operations when available.
- Use first-class `gh pr ...` / `gh issue ...` commands when they exist.
- If there is no first-class command, use `gh api` instead of manual browser-only workflows.
- For repeated GitHub review housekeeping, prefer a helper script or documented workflow over ad hoc command reconstruction.
- After addressing an inline PR review comment, reply and resolve the thread in the same session. Use `make gh-resolve-review-thread GH_ARGS='--pr <pr> --comment-id <id> --body-file <path>'` or `--body '...'` instead of leaving addressed threads open.
- bring local main branch up to date after merge if you can

## Verification
- Run the smallest relevant tests/lint/build for the changed slice.
- for UI/workflow changes, prefer automated smoke first
- Report exactly what ran and what did not run.
- Do not claim completion without fresh verification.
