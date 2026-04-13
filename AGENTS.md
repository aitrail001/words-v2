
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


## Git and GitHub

- Keep branches and commits focused.
- Do not mix unrelated cleanup into a feature change.
- Avoid destructive git commands unless explicitly requested.
- Prefer `gh` for GitHub operations when available.
- Use first-class `gh pr ...` / `gh issue ...` commands when they exist.
- If there is no first-class command, use `gh api` instead of manual browser-only workflows.
- Prefer `make pr-open GH_ARGS='...'` over raw `gh pr create` when opening a review PR so `gate-full` is enforced first.
- For repeated GitHub review housekeeping, prefer a helper script or documented workflow over ad hoc command reconstruction.
- After addressing an inline PR review comment, reply and resolve the thread in the same session. Use `make gh-resolve-review-thread GH_ARGS='--pr <pr> --comment-id <id> --body-file <path>'` or `--body '...'` instead of leaving addressed threads open.
- bring local main branch up to date after merge if you can

## Verification
- Run the smallest relevant tests/lint/build for the changed slice.
- for UI/workflow changes, prefer automated smoke first
- Report exactly what ran and what did not run.
- Do not claim completion without fresh verification.


## PR verification policy for Codex and humans

### Local CI and GitHub gate

- Treat `make test-backend`, `make test-frontend`, `make test-admin`, and `make smoke-local` as inner-loop checks only.
- Treat `gate-fast` and `gate-full` as the canonical local readiness entry points.
- Keep `local-ci-*` only for CI-like stack/debugging workflows, not as the primary local readiness path.
- For Codex runs, `make gate-fast`, `make gate-full`, and `scripts/ci/run-e2e-suite.sh *` must be run outside the sandbox on the first attempt.
- Do not try those gate commands in the sandbox first.
- Reason: they rely on Docker/Buildx and disposable test stacks, and sandbox failures are usually environmental noise rather than useful verification.
- After each non-trivial change set, or Before push and before asking for review-facing feedback on a branch, run `make gate-fast`.
- Before opening a PR, marking a PR ready, or pushing a PR update intended for review, run `make gate-full`.
- Prefer `make pr-open GH_ARGS='...'` for opening PRs so the `gate-full` requirement is enforced by the repo workflow instead of memory alone.
- Do not open or update a PR for review if `make gate-full` fails unless the user explicitly asks for a failing PR.
- When reporting verification, include the exact command run and whether it passed or failed.

### CI implementation rule

- GitHub workflows, including `.github/workflows/ci.yml`, must stay thin wrappers around repo-owned CI scripts and commands.
- Do not duplicate complex stack startup, readiness checks, migrations, test grouping, or artifact collection logic inline in `.github/workflows/*.yml` when the same behavior already exists in repo scripts.
- Put the real logic in `scripts/ci/*` and have both local gates and GitHub workflows call those scripts.
- Structured outputs from `scripts/ci/*` land under `artifacts/ci-gate/<label>`.

### Gate maintenance rule

When adding, removing, renaming, or reclassifying tests that affect release confidence:
- start in `scripts/ci/test-groups.sh` for any CI-relevant test additions, removals, or reclassifications
- update the shared suite definitions first
- update `gate-fast` / `gate-full` in the same PR
- update GitHub workflow wiring in the same PR if job boundaries or required checks change
- do not leave local gates and GitHub gates out of sync
- Keep fail-fast ordering in GitHub gate:
  1. backend / frontend / admin-frontend / lexicon
  2. `e2e-smoke`
  3. `e2e-review-srs`, `e2e-admin`, `e2e-user` and any other full e2e tests

### Test grouping rule

- Keep fast/high-signal backend tests in a shared backend subset definition, not hardcoded in multiple places.
- Keep E2E suite groupings in shared CI scripts or manifests, with `scripts/ci/test-groups.sh` as the starting point for CI-relevant test grouping changes, not duplicated across Makefiles and workflow YAML.

### Playwright artifact rule

- Do not make multiple repo-owned E2E runners write to the same Playwright report folder.
- Gate and CI E2E runs write per-suite artifacts under `artifacts/ci-gate/<suite>/playwright/`.
- Scripted local wrappers write to runner-specific folders under `e2e/artifacts/<runner>/`.
- Raw ad hoc `npm --prefix e2e ...` or `playwright test` runs may use the default `e2e/playwright-report` and `e2e/test-results`, but any new repo-owned wrapper must set explicit `PLAYWRIGHT_HTML_OUTPUT_DIR`, `PLAYWRIGHT_RESULTS_DIR`, and `PLAYWRIGHT_JUNIT_OUTPUT_FILE`.


### Gate stack
- Use the disposable PR gate stack for PR verification:
  - `compose.infra.gate.yml + compose.teststack.yml (+ compose.e2e.yml)`
  - `.env.stack.gate`
  - `docker compose down -v  --remove-orphans` is allowed for this disposable stack, and you should when finish because it is supposed to be disposable.
- Do not use the shared persistent test stack as PR sign-off.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `uv run --with graphifyy python3.13 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` to keep the graph current
