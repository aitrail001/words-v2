#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

cd_repo_root
load_env
init_gate_artifacts "gate-full"
trap 'finalize_gate_artifacts "gate-full" "failed"' ERR

record_gate_step "gate-full" "gate-fast-phase" "gate-fast"
"${SCRIPT_DIR}/gate-fast.sh"
append_gate_summary "gate-full" "gate_fast_summary=artifacts/ci-gate/gate-fast/summary.log"
append_gate_summary "gate-full" "gate_fast_steps=artifacts/ci-gate/gate-fast/steps.log"

is_skipped_mode() {
  local mode="$1"
  shift
  local skipped_mode
  for skipped_mode in "$@"; do
    if [[ "${skipped_mode}" == "${mode}" ]]; then
      return 0
    fi
  done
  return 1
}

print_section "Full backend suite"
record_gate_step "gate-full" "backend-full" "backend-full"
"${SCRIPT_DIR}/run-backend-suite.sh" full

print_section "Full frontend test suite"
for mode in "${FRONTEND_FULL_MODES[@]}"; do
  if is_skipped_mode "${mode}" "${FRONTEND_FAST_MODES[@]}"; then
    continue
  fi
  record_gate_step "gate-full" "frontend-${mode}" "frontend-${mode}"
  "${SCRIPT_DIR}/run-frontend-suite.sh" "${mode}"
done

print_section "Admin production build"
for mode in "${ADMIN_FULL_MODES[@]}"; do
  if is_skipped_mode "${mode}" "${ADMIN_FAST_MODES[@]}"; then
    continue
  fi
  record_gate_step "gate-full" "admin-${mode}" "admin-${mode}"
  "${SCRIPT_DIR}/run-admin-suite.sh" "${mode}"
done

print_section "Full lexicon suite"
record_gate_step "gate-full" "lexicon-full" "lexicon-full"
"${SCRIPT_DIR}/run-lexicon-suite.sh" full

for suite in "${E2E_REQUIRED_FULL_SUITES[@]}"; do
  record_gate_step "gate-full" "e2e-${suite}" "e2e-${suite}"
  "${SCRIPT_DIR}/run-e2e-suite.sh" "${suite}"
done

append_gate_summary "gate-full" "steps_log=artifacts/ci-gate/gate-full/steps.log"
append_gate_summary "gate-full" "suite_logs=artifacts/ci-gate/backend-full artifacts/ci-gate/frontend-build artifacts/ci-gate/admin-build artifacts/ci-gate/lexicon-full"
for suite in "${E2E_REQUIRED_FULL_SUITES[@]}"; do
  append_gate_summary "gate-full" "suite_logs+=artifacts/ci-gate/e2e-${suite}"
done
finalize_gate_artifacts "gate-full" "passed"
trap - ERR

print_section "gate-full passed"
