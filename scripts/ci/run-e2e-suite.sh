#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

suite="${1:-smoke}"
npm_script=""
label=""

case "${suite}" in
  smoke)
    npm_script="test:smoke:ci"
    label="e2e-smoke"
    ;;
  review-srs)
    npm_script="test:review:ci"
    label="e2e-review-srs"
    ;;
  admin)
    npm_script="test:admin"
    label="e2e-admin"
    ;;
  user)
    npm_script="test:user"
    label="e2e-user"
    ;;
  full)
    npm_script="test:full"
    label="e2e-full"
    ;;
  *)
    echo "Unknown E2E suite '${suite}'. Use smoke|review-srs|admin|user|full." >&2
    exit 1
    ;;
esac

load_env

if [[ ! -d "${REPO_ROOT}/e2e/node_modules" ]]; then
  print_section "Installing E2E dependencies"
  run_logged "${label}" "npm-ci.log" bash -lc "cd '${REPO_ROOT}/e2e' && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm ci"
fi

cleanup() {
  local exit_code=$?
  collect_stack_logs "${label}"
  teardown_stack
  exit "${exit_code}"
}

trap cleanup EXIT

start_stack "${label}"
apply_migrations "${label}"

print_section "Running Playwright suite: ${npm_script}"
run_playwright_script "${label}" "${npm_script}"

trap - EXIT
collect_stack_logs "${label}"
teardown_stack
