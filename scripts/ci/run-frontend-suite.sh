#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

suite="${1:-full}"
label="frontend-${suite}"

cd_repo_root
load_env

run_frontend() {
  (
    cd frontend
    "$@"
  )
}

run_mode_sequence() {
  local mode
  for mode in "$@"; do
    case "${mode}" in
      lint)
        run_lint
        ;;
      subset)
        run_subset
        ;;
      test)
        run_test
        ;;
      build)
        run_build
        ;;
      *)
        die "Unknown frontend mode '${mode}'."
        ;;
    esac
  done
}

run_lint() {
  print_section "Frontend lint"
  run_logged "${label}" "lint.log" run_frontend npm run lint
}

run_subset() {
  print_section "Frontend Review + SRS regression subset"
  run_logged "${label}" "subset.log" run_frontend "${FAST_FRONTEND_SUBSET_COMMAND[@]}"
}

run_test() {
  print_section "Frontend test"
  run_logged "${label}" "test.log" run_frontend npm test -- --runInBand
}

run_build() {
  print_section "Frontend build"
  run_logged "${label}" "build.log" env BACKEND_URL=http://backend:8000/api NEXT_PUBLIC_API_URL=http://backend:8000/api bash -lc 'cd frontend && npm run build'
}

case "${suite}" in
  lint)
    run_lint
    ;;
  subset)
    run_subset
    ;;
  test)
    run_test
    ;;
  build)
    run_build
    ;;
  fast)
    run_mode_sequence "${FRONTEND_FAST_MODES[@]}"
    ;;
  full)
    run_mode_sequence "${FRONTEND_FULL_MODES[@]}"
    ;;
  *)
    die "Unknown frontend suite '${suite}'. Use lint, subset, test, build, fast, or full."
    ;;
esac
