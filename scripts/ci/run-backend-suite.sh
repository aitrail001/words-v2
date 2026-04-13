#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

suite="${1:-full}"
label="backend-${suite}"

load_env

cleanup() {
  local exit_code=$?
  collect_infra_logs "${label}"
  teardown_infra
  exit "${exit_code}"
}

trap cleanup EXIT

start_infra "${label}"

case "${suite}" in
  subset)
    print_section "Running backend Review + SRS regression subset"
    run_logged "${label}" "pytest.log" run_backend_pytest "${FAST_BACKEND_SUBSET[@]}"
    ;;
  full)
    print_section "Running full backend pytest suite"
    run_logged "${label}" "pytest.log" run_backend_pytest
    ;;
  *)
    die "Unknown backend suite '${suite}'. Use 'subset' or 'full'."
    ;;
esac

trap - EXIT
collect_infra_logs "${label}"
teardown_infra
