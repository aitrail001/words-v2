#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

suite="${1:-smoke}"
npm_script=""
label=""
label_suffix="${PLAYWRIGHT_LABEL_SUFFIX:-}"

case "${suite}" in
  smoke)
    npm_script="test:smoke:ci"
    label="e2e-smoke"
    ;;
  route-runtime-smoke)
    npm_script="test:route-runtime:smoke"
    label="e2e-route-runtime-smoke"
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
  route-runtime-full)
    npm_script="test:route-runtime:full"
    label="e2e-route-runtime-full"
    ;;
  full)
    npm_script="test:full"
    label="e2e-full"
    ;;
  *)
    echo "Unknown E2E suite '${suite}'. Use smoke|route-runtime-smoke|review-srs|admin|user|route-runtime-full|full." >&2
    exit 1
    ;;
esac

label="${label}${label_suffix}"

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
