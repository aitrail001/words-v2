#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

cd_repo_root
load_env

print_section "PR sign-off gate"
"${SCRIPT_DIR}/gate-full.sh"

print_section "Creating pull request"
gh pr create "$@"
