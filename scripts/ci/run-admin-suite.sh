#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/test-groups.sh"

suite="${1:-full}"
label="admin-${suite}"

cd_repo_root
load_env

run_admin() {
  (
    cd admin-frontend
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
      test)
        run_test
        ;;
      build)
        run_build
        ;;
      *)
        die "Unknown admin frontend mode '${mode}'."
        ;;
    esac
  done
}

run_lint() {
  print_section "Admin frontend lint"
  run_logged "${label}" "lint.log" run_admin npm run lint
}

run_test() {
  print_section "Admin frontend test"
  run_logged "${label}" "test.log" run_admin npm test -- --runInBand
}

run_build() {
  print_section "Admin frontend build"
  run_logged "${label}" "build.log" env BACKEND_URL=http://backend:8000/api NEXT_PUBLIC_API_URL=http://backend:8000/api bash -lc 'cd admin-frontend && npm run build'
}

case "${suite}" in
  lint)
    run_lint
    ;;
  test)
    run_test
    ;;
  build)
    run_build
    ;;
  fast)
    run_mode_sequence "${ADMIN_FAST_MODES[@]}"
    ;;
  full)
    run_mode_sequence "${ADMIN_FULL_MODES[@]}"
    ;;
  *)
    die "Unknown admin frontend suite '${suite}'. Use lint, test, build, fast, or full."
    ;;
esac
