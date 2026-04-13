# CI Workflow Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify local gates and GitHub CI around repo-owned `scripts/ci/*` runners so local `gate-fast` / `gate-full` exercise the same suite definitions and lane behavior as `.github/workflows/ci.yml`.

**Architecture:** Keep the current GitHub job graph, but move lane behavior into dedicated `scripts/ci/*` runners backed by a shared `test-groups.sh` manifest and common `lib.sh` helpers. Make `gate-fast` / `gate-full` the canonical readiness entry points, retain `local-ci-*` only as debugging wrappers, and normalize structured outputs under `artifacts/ci-gate/<label>`.

**Tech Stack:** Bash, GNU Make, GitHub Actions, Docker Compose, pytest, npm/Jest, Playwright, FastAPI, Next.js

---

## File Structure

### Modify

- `.github/workflows/ci.yml`
  Purpose: keep the existing required job topology, but reduce each job to setup plus invocation of repo-owned scripts and artifact upload.
- `AGENTS.md`
  Purpose: codify `.env.stack.gate`, `gate-fast` / `gate-full` as canonical readiness commands, `local-ci-*` as debug utilities, and `scripts/ci/test-groups.sh` as the first update point for suite changes.
- `Makefile`
  Purpose: align `gate-*` and `local-ci-*` targets with the new runner layer and update help text to reflect the narrowed meaning of `local-ci-*`.
- `scripts/ci/lib.sh`
  Purpose: centralize normalized artifact-root handling, shared stack helpers, and any common helper functions needed by all suite runners.
- `scripts/ci/test-groups.sh`
  Purpose: act as the canonical manifest for CI-relevant suite membership and lane grouping.
- `scripts/ci/run-backend-suite.sh`
  Purpose: read backend subset membership from `test-groups.sh` and stay the single backend runner entry point.
- `scripts/ci/run-e2e-suite.sh`
  Purpose: keep named E2E suite execution in the script layer and support reuse by both gates and `local-ci-*`.
- `scripts/ci/gate-fast.sh`
  Purpose: compose the fail-fast local readiness gate from runner scripts only.
- `scripts/ci/gate-full.sh`
  Purpose: compose the full local readiness gate from runner scripts only and mirror the required GitHub gate lanes.

### Create

- `scripts/ci/run-frontend-suite.sh`
  Purpose: encapsulate frontend lint, subset test, full test, build, and aggregate gate modes.
- `scripts/ci/run-admin-suite.sh`
  Purpose: encapsulate admin frontend lint, test, build, and aggregate gate modes.
- `scripts/ci/run-lexicon-suite.sh`
  Purpose: encapsulate lexicon full test, smoke, and aggregate gate modes.

### Verification targets

- `make gate-fast`
- focused shell execution sanity for new runner scripts via `bash -n`
- CI workflow validation via GitHub Actions parsing available in-repo (`gh workflow view` is not required for this plan)

### Task 1: Normalize Shared CI Helpers and Test Group Definitions

**Files:**
- Modify: `scripts/ci/lib.sh`
- Modify: `scripts/ci/test-groups.sh`
- Test: `scripts/ci/lib.sh`
- Test: `scripts/ci/test-groups.sh`

- [ ] **Step 1: Write the failing policy check by inspecting the current artifact root and repeated suite definitions**

Run:

```bash
rg -n "artifacts/local-ci|FAST_BACKEND_SUBSET|E2E_FAST_SUITES|E2E_FULL_SUITES" scripts/ci/lib.sh scripts/ci/test-groups.sh scripts/ci/run-backend-suite.sh
```

Expected: `lib.sh` still points at `artifacts/local-ci`, and `run-backend-suite.sh` still hardcodes the backend subset rather than consuming only `test-groups.sh`.

- [ ] **Step 2: Update `scripts/ci/lib.sh` to use the normalized gate artifact root and expose a reusable label-path helper**

Apply this change:

```bash
cat <<'EOF'
Set:
- LOG_ROOT="${LOG_ROOT:-${REPO_ROOT}/artifacts/ci-gate}"

Add helper:
artifact_dir() {
  local label="$1"
  local out_dir="${LOG_ROOT}/${label}"
  mkdir -p "${out_dir}"
  printf '%s\n' "${out_dir}"
}

Update collect_infra_logs() and collect_stack_logs() to call artifact_dir "${label}"
instead of manually constructing "${LOG_ROOT}/${label}".
EOF
```

- [ ] **Step 3: Expand `scripts/ci/test-groups.sh` into the canonical suite manifest**

Apply this change:

```bash
cat <<'EOF'
Keep FAST_BACKEND_SUBSET as the canonical backend subset array.

Keep FAST_FRONTEND_SUBSET_COMMAND as the canonical frontend fast-check command array.

Add explicit mode/group arrays or constants for:
- E2E_SMOKE_SUITES=(smoke)
- E2E_REQUIRED_FULL_SUITES=(review-srs admin user)
- FRONTEND_FAST_MODES=(lint subset)
- FRONTEND_FULL_MODES=(lint subset test build)
- ADMIN_FAST_MODES=(lint test)
- ADMIN_FULL_MODES=(lint test build)
- LEXICON_GATE_MODES=(full smoke)

Keep comments stating:
"Update this file first when CI-relevant tests or lane memberships change."
EOF
```

- [ ] **Step 4: Run shell syntax checks**

Run:

```bash
bash -n scripts/ci/lib.sh scripts/ci/test-groups.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/ci/lib.sh scripts/ci/test-groups.sh
git commit -m "refactor: normalize ci gate helpers and test groups"
```

### Task 2: Make the Backend Runner Consume Shared Group Definitions

**Files:**
- Modify: `scripts/ci/run-backend-suite.sh`
- Modify: `scripts/ci/test-groups.sh`
- Test: `scripts/ci/run-backend-suite.sh`

- [ ] **Step 1: Write the failing consistency check**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path("scripts/ci/run-backend-suite.sh").read_text()
assert "tests/test_imports_api.py" in text, "expected hardcoded backend subset entries before refactor"
PY
```

Expected: command exits 0, proving the runner still duplicates subset membership.

- [ ] **Step 2: Update the backend runner to source `test-groups.sh` and pass the shared array**

Implement this shape:

```bash
cat <<'EOF'
Near the top:
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

In subset mode:
run_backend_pytest "${FAST_BACKEND_SUBSET[@]}"

Remove the inline repeated test-file list from the case statement.
EOF
```

- [ ] **Step 3: Verify the hardcoded file list is gone from the runner**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path("scripts/ci/run-backend-suite.sh").read_text()
assert "tests/test_imports_api.py" not in text, "backend subset list should live only in test-groups.sh"
assert 'FAST_BACKEND_SUBSET[@]' in text, "backend runner should execute the shared subset array"
PY
```

Expected: command exits 0.

- [ ] **Step 4: Run shell syntax checks**

Run:

```bash
bash -n scripts/ci/run-backend-suite.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/ci/run-backend-suite.sh scripts/ci/test-groups.sh
git commit -m "refactor: source backend ci subset from shared groups"
```

### Task 3: Add Frontend and Admin Runner Scripts

**Files:**
- Create: `scripts/ci/run-frontend-suite.sh`
- Create: `scripts/ci/run-admin-suite.sh`
- Modify: `scripts/ci/test-groups.sh`
- Test: `scripts/ci/run-frontend-suite.sh`
- Test: `scripts/ci/run-admin-suite.sh`

- [ ] **Step 1: Write the failing existence check**

Run:

```bash
test -f scripts/ci/run-frontend-suite.sh && test -f scripts/ci/run-admin-suite.sh
```

Expected: FAIL because the runner scripts do not exist yet.

- [ ] **Step 2: Create `scripts/ci/run-frontend-suite.sh`**

Create this file:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

mode="${1:-full}"

run_lint() {
  print_section "Frontend lint"
  (cd "${REPO_ROOT}/frontend" && npm run lint)
}

run_subset() {
  print_section "Frontend review + SRS regression subset"
  (cd "${REPO_ROOT}/frontend" && "${FAST_FRONTEND_SUBSET_COMMAND[@]}")
}

run_test() {
  print_section "Frontend full test suite"
  (cd "${REPO_ROOT}/frontend" && npm test -- --runInBand)
}

run_build() {
  print_section "Frontend production build"
  (cd "${REPO_ROOT}/frontend" && NEXT_PUBLIC_API_URL=http://backend:8000/api npm run build)
}

case "${mode}" in
  lint) run_lint ;;
  subset) run_subset ;;
  test) run_test ;;
  build) run_build ;;
  fast)
    run_lint
    run_subset
    ;;
  full)
    run_lint
    run_subset
    run_test
    run_build
    ;;
  *)
    die "Unknown frontend suite '${mode}'. Use lint|subset|test|build|fast|full."
    ;;
esac
```

- [ ] **Step 3: Create `scripts/ci/run-admin-suite.sh`**

Create this file:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

mode="${1:-full}"

run_lint() {
  print_section "Admin frontend lint"
  (cd "${REPO_ROOT}/admin-frontend" && npm run lint)
}

run_test() {
  print_section "Admin frontend test"
  (cd "${REPO_ROOT}/admin-frontend" && npm test -- --runInBand)
}

run_build() {
  print_section "Admin frontend production build"
  (cd "${REPO_ROOT}/admin-frontend" && NEXT_PUBLIC_API_URL=http://backend:8000/api npm run build)
}

case "${mode}" in
  lint) run_lint ;;
  test) run_test ;;
  build) run_build ;;
  fast)
    run_lint
    run_test
    ;;
  full)
    run_lint
    run_test
    run_build
    ;;
  *)
    die "Unknown admin suite '${mode}'. Use lint|test|build|fast|full."
    ;;
esac
```

- [ ] **Step 4: Mark the scripts executable**

Run:

```bash
chmod +x scripts/ci/run-frontend-suite.sh scripts/ci/run-admin-suite.sh
```

Expected: command exits 0.

- [ ] **Step 5: Run shell syntax checks**

Run:

```bash
bash -n scripts/ci/run-frontend-suite.sh scripts/ci/run-admin-suite.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/ci/run-frontend-suite.sh scripts/ci/run-admin-suite.sh scripts/ci/test-groups.sh
git commit -m "refactor: add frontend and admin ci runners"
```

### Task 4: Add a Dedicated Lexicon Runner Script

**Files:**
- Create: `scripts/ci/run-lexicon-suite.sh`
- Test: `scripts/ci/run-lexicon-suite.sh`

- [ ] **Step 1: Write the failing existence check**

Run:

```bash
test -f scripts/ci/run-lexicon-suite.sh
```

Expected: FAIL because the script does not exist yet.

- [ ] **Step 2: Create `scripts/ci/run-lexicon-suite.sh`**

Create this file:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

mode="${1:-gate}"

run_full() {
  print_section "Lexicon full test suite"
  make ci-test-lexicon
}

run_smoke() {
  print_section "Lexicon smoke flow"
  export LEXICON_SKIP_VENV_GUARD="1"
  smoke_dir="${TMPDIR:-/tmp}/lexicon-smoke"
  rm -rf "${smoke_dir}"
  mkdir -p "${smoke_dir}"
  python -m tools.lexicon.cli build-base run set lead --output-dir "${smoke_dir}"
  python -m tools.lexicon.cli enrich --snapshot-dir "${smoke_dir}" --provider-mode placeholder
  python -m tools.lexicon.cli validate --snapshot-dir "${smoke_dir}"
  test -f "${smoke_dir}/words.enriched.jsonl"
  python - <<'PY' "${smoke_dir}/words.enriched.jsonl"
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
assert rows, "expected at least one compiled word row"
phonetics = rows[0]["phonetics"]
assert set(phonetics.keys()) == {"us", "uk", "au"}
assert all(isinstance(phonetics[accent]["ipa"], str) and phonetics[accent]["ipa"] for accent in ("us", "uk", "au"))
PY
}

case "${mode}" in
  full) run_full ;;
  smoke) run_smoke ;;
  gate)
    run_full
    run_smoke
    ;;
  *)
    die "Unknown lexicon suite '${mode}'. Use full|smoke|gate."
    ;;
esac
```

- [ ] **Step 3: Mark the script executable**

Run:

```bash
chmod +x scripts/ci/run-lexicon-suite.sh
```

Expected: command exits 0.

- [ ] **Step 4: Run shell syntax checks**

Run:

```bash
bash -n scripts/ci/run-lexicon-suite.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/ci/run-lexicon-suite.sh
git commit -m "refactor: add lexicon ci runner"
```

### Task 5: Refactor the Gate Scripts to Use Only Runner Scripts

**Files:**
- Modify: `scripts/ci/gate-fast.sh`
- Modify: `scripts/ci/gate-full.sh`
- Test: `scripts/ci/gate-fast.sh`
- Test: `scripts/ci/gate-full.sh`

- [ ] **Step 1: Write the failing duplication check**

Run:

```bash
python - <<'PY'
from pathlib import Path
fast = Path("scripts/ci/gate-fast.sh").read_text()
full = Path("scripts/ci/gate-full.sh").read_text()
assert "(cd frontend && npm run lint)" in fast
assert "(cd admin-frontend && npm test -- --runInBand)" in fast
assert "make test-lexicon" in full
PY
```

Expected: command exits 0, proving the gates still contain inline lane commands.

- [ ] **Step 2: Refactor `scripts/ci/gate-fast.sh` to call runner scripts only**

Update the body to this shape:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

cd_repo_root
load_env

print_section "Bootstrapping worktree"
make worktree-bootstrap

print_section "Backend lint"
make lint-backend

"${SCRIPT_DIR}/run-frontend-suite.sh" fast
"${SCRIPT_DIR}/run-admin-suite.sh" fast
"${SCRIPT_DIR}/run-backend-suite.sh" subset
"${SCRIPT_DIR}/run-lexicon-suite.sh" gate
"${SCRIPT_DIR}/run-e2e-suite.sh" smoke

print_section "gate-fast passed"
```

- [ ] **Step 3: Refactor `scripts/ci/gate-full.sh` to build on `gate-fast` and runner scripts only**

Update the body to this shape:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

cd_repo_root
load_env

"${SCRIPT_DIR}/gate-fast.sh"
"${SCRIPT_DIR}/run-backend-suite.sh" full
"${SCRIPT_DIR}/run-frontend-suite.sh" full
"${SCRIPT_DIR}/run-admin-suite.sh" full
"${SCRIPT_DIR}/run-e2e-suite.sh" review-srs
"${SCRIPT_DIR}/run-e2e-suite.sh" admin
"${SCRIPT_DIR}/run-e2e-suite.sh" user

print_section "gate-full passed"
```

- [ ] **Step 4: Verify the inline lane commands are gone**

Run:

```bash
python - <<'PY'
from pathlib import Path
fast = Path("scripts/ci/gate-fast.sh").read_text()
full = Path("scripts/ci/gate-full.sh").read_text()
assert "(cd frontend && npm run lint)" not in fast
assert "(cd admin-frontend && npm test -- --runInBand)" not in fast
assert "make test-lexicon" not in full
assert 'run-frontend-suite.sh" fast' in fast
assert 'run-admin-suite.sh" full' in full
PY
```

Expected: command exits 0.

- [ ] **Step 5: Run shell syntax checks**

Run:

```bash
bash -n scripts/ci/gate-fast.sh scripts/ci/gate-full.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/ci/gate-fast.sh scripts/ci/gate-full.sh
git commit -m "refactor: compose local gates from ci runners"
```

### Task 6: Align `local-ci-*` and Gate Targets in the Makefile

**Files:**
- Modify: `Makefile`
- Test: `Makefile`

- [ ] **Step 1: Write the failing help-text and target wiring check**

Run:

```bash
rg -n "local-ci-smoke|local-ci-full|CI-style stack|fail-fast pre-push / pre-PR gate" Makefile
```

Expected: output still describes `local-ci-*` as CI-style execution commands without clarifying their debugging role, and `local-ci-smoke/full` still run direct compose Playwright commands.

- [ ] **Step 2: Update `local-ci-smoke` and `local-ci-full` to be thin wrappers over the runner scripts**

Apply this change:

```bash
cat <<'EOF'
Replace:
local-ci-smoke:
	$(CI_E2E_COMPOSE) --profile tests run --rm playwright npm run test:smoke:ci

local-ci-full:
	$(CI_E2E_COMPOSE) --profile tests run --rm playwright npm run test:full

With:
local-ci-smoke: chmod-scripts
	ENV_FILE=$(GATE_ENV_FILE) ./scripts/ci/run-e2e-suite.sh smoke

local-ci-full: chmod-scripts
	ENV_FILE=$(GATE_ENV_FILE) ./scripts/ci/run-e2e-suite.sh full
EOF
```

- [ ] **Step 3: Update the help text to narrow `local-ci-*` to debugging utilities and reinforce `gate-fast` / `gate-full`**

Apply this wording change:

```bash
cat <<'EOF'
Change help lines so they read like:
- make local-ci-up           # start disposable CI-like stack for debugging
- make local-ci-build        # rebuild/start disposable CI-like stack for debugging
- make local-ci-down         # stop disposable CI-like stack
- make local-ci-logs         # tail disposable CI-like stack logs
- make local-ci-ps           # show disposable CI-like stack containers
- make local-ci-restart      # restart disposable CI-like stack containers
- make local-ci-smoke        # run smoke suite through scripts/ci against the gate stack
- make local-ci-full         # run full E2E suite through scripts/ci against the gate stack
- make gate-fast             # canonical fail-fast pre-push / pre-review gate
- make gate-full             # canonical full pre-PR / pre-review gate
EOF
```

- [ ] **Step 4: Verify the new target wiring**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path("Makefile").read_text()
assert 'ENV_FILE=$(GATE_ENV_FILE) ./scripts/ci/run-e2e-suite.sh smoke' in text
assert 'ENV_FILE=$(GATE_ENV_FILE) ./scripts/ci/run-e2e-suite.sh full' in text
PY
```

Expected: command exits 0.

- [ ] **Step 5: Commit**

```bash
git add Makefile
git commit -m "refactor: align make ci wrappers with gate scripts"
```

### Task 7: Refactor `.github/workflows/ci.yml` Into Thin Script Wrappers

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the failing duplication check**

Run:

```bash
rg -n "Backend health endpoint did not become ready in time|Frontend did not become ready in time|docker compose .*up -d --build --force-recreate|pytest -q tests/test_imports_api.py|npm run test:review|python -m tools.lexicon.cli build-base" .github/workflows/ci.yml
```

Expected: multiple matches, proving the workflow still owns duplicated lane logic.

- [ ] **Step 2: Refactor the backend job to call the backend runner**

Update the backend job so the run steps converge to:

```yaml
      - name: Backend subset
        env:
          DATABASE_URL: postgresql+asyncpg://vocabapp:testpass@localhost:5432/vocabapp_test
          DATABASE_URL_SYNC: postgresql://vocabapp:testpass@localhost:5432/vocabapp_test
          REDIS_URL: redis://localhost:6379
          ENVIRONMENT: test
          JWT_SECRET: test-secret
        run: ./scripts/ci/run-backend-suite.sh subset

      - name: Backend full
        env:
          DATABASE_URL: postgresql+asyncpg://vocabapp:testpass@localhost:5432/vocabapp_test
          DATABASE_URL_SYNC: postgresql://vocabapp:testpass@localhost:5432/vocabapp_test
          REDIS_URL: redis://localhost:6379
          ENVIRONMENT: test
          JWT_SECRET: test-secret
        run: ./scripts/ci/run-backend-suite.sh full
```

Keep Python setup and dependency installation in YAML. Do not keep inline subset file lists.

- [ ] **Step 3: Refactor the frontend, admin frontend, and lexicon jobs to call their runner scripts**

Update the jobs so the run steps converge to:

```yaml
      - name: Frontend full gate
        run: ./scripts/ci/run-frontend-suite.sh full

      - name: Admin frontend full gate
        run: ./scripts/ci/run-admin-suite.sh full

      - name: Lexicon gate
        run: ./scripts/ci/run-lexicon-suite.sh gate
```

Keep runtime setup and package installation in YAML. Remove inline lane command duplication from the workflow.

- [ ] **Step 4: Refactor each E2E job to call `run-e2e-suite.sh` with a named mode**

Update the E2E jobs so the run steps converge to:

```yaml
      - name: Run Playwright smoke suite
        run: ENV_FILE=.env.stack.gate ./scripts/ci/run-e2e-suite.sh smoke

      - name: Run Playwright review + SRS suite
        run: ENV_FILE=.env.stack.gate ./scripts/ci/run-e2e-suite.sh review-srs

      - name: Run Playwright admin suite
        run: ENV_FILE=.env.stack.gate ./scripts/ci/run-e2e-suite.sh admin

      - name: Run Playwright user suite
        run: ENV_FILE=.env.stack.gate ./scripts/ci/run-e2e-suite.sh user
```

Also:

- add a preparatory step that writes a CI-specific `.env.stack.gate` file with the GitHub runner values already declared in workflow env
- remove inline compose startup, readiness loops, migration runs, log collection, and teardown blocks that the script layer now owns
- keep artifact upload steps, but point them at `artifacts/ci-gate/<label>` plus Playwright result directories

- [ ] **Step 5: Verify the workflow no longer contains the duplicated inline lane logic**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path(".github/workflows/ci.yml").read_text()
for needle in [
    "Backend health endpoint did not become ready in time.",
    "Frontend did not become ready in time.",
    "Admin frontend did not become ready in time.",
    "python -m tools.lexicon.cli build-base",
]:
    assert needle not in text, f"workflow should not keep inline gate logic: {needle}"
for needle in [
    "./scripts/ci/run-backend-suite.sh subset",
    "./scripts/ci/run-frontend-suite.sh full",
    "./scripts/ci/run-admin-suite.sh full",
    "./scripts/ci/run-lexicon-suite.sh gate",
    "./scripts/ci/run-e2e-suite.sh smoke",
]:
    assert needle in text, f"expected workflow to invoke repo-owned script: {needle}"
PY
```

Expected: command exits 0.

- [ ] **Step 6: Run YAML syntax parsing through Python**

Run:

```bash
python - <<'PY'
import yaml
from pathlib import Path
yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
print("ci.yml parsed")
PY
```

Expected: output `ci.yml parsed`.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "refactor: make github ci call repo-owned gate scripts"
```

### Task 8: Update Repo Policy and Verify the Unified Gate Contract

**Files:**
- Modify: `AGENTS.md`
- Test: `AGENTS.md`
- Test: `scripts/ci/*.sh`
- Test: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the failing policy consistency check**

Run:

```bash
rg -n "\.env\.stack\.pr|local-ci-\*|scripts/ci/test-groups\.sh|artifacts/ci-gate|gate-fast|gate-full" AGENTS.md
```

Expected: `AGENTS.md` still mentions `.env.stack.pr` and does not yet fully describe `local-ci-*` as debugging utilities or `artifacts/ci-gate` as the normalized output root.

- [ ] **Step 2: Update `AGENTS.md` to match the approved contract**

Make these edits:

```bash
cat <<'EOF'
- Replace `.env.stack.pr` with `.env.stack.gate`.
- Clarify that `gate-fast` and `gate-full` are the canonical local readiness entry points.
- Clarify that `local-ci-*` is retained only for CI-like stack/debugging workflows.
- Add explicit wording that CI-relevant test additions/removals/reclassifications begin in `scripts/ci/test-groups.sh`.
- Add wording that structured outputs from `scripts/ci/*` land under `artifacts/ci-gate/<label>`.
- Keep the thin-wrapper rule for `.github/workflows/ci.yml`.
EOF
```

- [ ] **Step 3: Run shell syntax checks for the full CI script layer**

Run:

```bash
bash -n scripts/ci/lib.sh \
  scripts/ci/test-groups.sh \
  scripts/ci/run-backend-suite.sh \
  scripts/ci/run-frontend-suite.sh \
  scripts/ci/run-admin-suite.sh \
  scripts/ci/run-lexicon-suite.sh \
  scripts/ci/run-e2e-suite.sh \
  scripts/ci/gate-fast.sh \
  scripts/ci/gate-full.sh
```

Expected: command exits 0 with no output.

- [ ] **Step 4: Run the canonical fail-fast gate**

Run:

```bash
make gate-fast
```

Expected: PASS. The command should run through the repo-owned runner layer and emit structured outputs under `artifacts/ci-gate/<label>` for suite-running commands.

- [ ] **Step 5: Run targeted verification for workflow and documentation consistency**

Run:

```bash
python - <<'PY'
from pathlib import Path
agents = Path("AGENTS.md").read_text()
assert ".env.stack.pr" not in agents
assert ".env.stack.gate" in agents
assert "scripts/ci/test-groups.sh" in agents
assert "artifacts/ci-gate/<label>" in agents
workflow = Path(".github/workflows/ci.yml").read_text()
assert "./scripts/ci/run-lexicon-suite.sh gate" in workflow
assert "./scripts/ci/run-e2e-suite.sh smoke" in workflow
PY
```

Expected: command exits 0.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md scripts/ci .github/workflows/ci.yml Makefile
git commit -m "docs: codify unified ci gate contract"
```

## Self-Review

- Spec coverage:
  - shared `scripts/ci/*` runner layer: covered by Tasks 1 through 7
  - dedicated lexicon runner: covered by Task 4
  - `test-groups.sh` as the first update point: covered by Tasks 1, 2, and 8
  - GitHub thin-wrapper CI: covered by Task 7
  - `local-ci-*` retained as debugging layer only: covered by Tasks 6 and 8
  - `.env.stack.gate` and normalized `artifacts/ci-gate/<label>`: covered by Tasks 1, 7, and 8
- Placeholder scan:
  - no `TODO`, `TBD`, or “implement later” markers remain
  - every file path and command is explicit
- Type and naming consistency:
  - uses one env-file name: `.env.stack.gate`
  - uses one artifact root: `artifacts/ci-gate/<label>`
  - uses one lexicon aggregate mode name: `gate`
