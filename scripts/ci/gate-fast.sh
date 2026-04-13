#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

cd_repo_root
load_env

print_section "Bootstrapping worktree"
run_logged "gate-fast" "worktree-bootstrap.log" make worktree-bootstrap

print_section "Backend lint"
run_logged "gate-fast" "backend-lint.log" make lint-backend

print_section "Frontend lint"
"${SCRIPT_DIR}/run-frontend-suite.sh" fast

print_section "Admin frontend fast suite"
"${SCRIPT_DIR}/run-admin-suite.sh" fast

"${SCRIPT_DIR}/run-backend-suite.sh" subset
"${SCRIPT_DIR}/run-lexicon-suite.sh" gate
for suite in "${E2E_SMOKE_SUITES[@]}"; do
  "${SCRIPT_DIR}/run-e2e-suite.sh" "${suite}"
done

print_section "gate-fast passed"
