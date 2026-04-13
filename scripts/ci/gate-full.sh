#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

cd_repo_root
load_env

"${SCRIPT_DIR}/gate-fast.sh"

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
"${SCRIPT_DIR}/run-backend-suite.sh" full

print_section "Full frontend test suite"
for mode in "${FRONTEND_FULL_MODES[@]}"; do
  if is_skipped_mode "${mode}" "${FRONTEND_FAST_MODES[@]}"; then
    continue
  fi
  "${SCRIPT_DIR}/run-frontend-suite.sh" "${mode}"
done

print_section "Admin production build"
for mode in "${ADMIN_FULL_MODES[@]}"; do
  if is_skipped_mode "${mode}" "${ADMIN_FAST_MODES[@]}"; then
    continue
  fi
  "${SCRIPT_DIR}/run-admin-suite.sh" "${mode}"
done

print_section "Full lexicon suite"
"${SCRIPT_DIR}/run-lexicon-suite.sh" full

for suite in "${E2E_REQUIRED_FULL_SUITES[@]}"; do
  "${SCRIPT_DIR}/run-e2e-suite.sh" "${suite}"
done

print_section "gate-full passed"
