#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

cd_repo_root
load_env
init_gate_artifacts "gate-fast"
trap 'finalize_gate_artifacts "gate-fast" "failed"' ERR

record_gate_step "gate-fast" "worktree-bootstrap" "gate-fast"

print_section "Bootstrapping worktree"
run_logged "gate-fast" "worktree-bootstrap.log" make worktree-bootstrap

record_gate_step "gate-fast" "backend-lint" "gate-fast"
print_section "Backend lint"
run_logged "gate-fast" "backend-lint.log" make lint-backend

record_gate_step "gate-fast" "frontend-fast" "frontend-lint"
print_section "Frontend lint"
"${SCRIPT_DIR}/run-frontend-suite.sh" fast

record_gate_step "gate-fast" "admin-fast" "admin-lint"
print_section "Admin frontend fast suite"
"${SCRIPT_DIR}/run-admin-suite.sh" fast

record_gate_step "gate-fast" "backend-subset" "backend-subset"
"${SCRIPT_DIR}/run-backend-suite.sh" subset
record_gate_step "gate-fast" "lexicon-gate" "lexicon-full"
"${SCRIPT_DIR}/run-lexicon-suite.sh" gate
for suite in "${E2E_SMOKE_SUITES[@]}"; do
  record_gate_step "gate-fast" "e2e-${suite}" "e2e-${suite}"
  "${SCRIPT_DIR}/run-e2e-suite.sh" "${suite}"
done

append_gate_summary "gate-fast" "steps_log=artifacts/ci-gate/gate-fast/steps.log"
append_gate_summary "gate-fast" "suite_logs=artifacts/ci-gate/backend-subset artifacts/ci-gate/frontend-lint artifacts/ci-gate/frontend-review artifacts/ci-gate/admin-lint artifacts/ci-gate/admin-test artifacts/ci-gate/lexicon-full artifacts/ci-gate/lexicon-smoke"
for suite in "${E2E_SMOKE_SUITES[@]}"; do
  append_gate_summary "gate-fast" "suite_logs+=artifacts/ci-gate/e2e-${suite}"
done
finalize_gate_artifacts "gate-fast" "passed"
trap - ERR

print_section "gate-fast passed"
