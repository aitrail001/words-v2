#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

suite="${1:-full}"
label="lexicon-${suite}"

cd_repo_root

lexicon_python() {
  if [[ -x "${REPO_ROOT}/.venv-lexicon/bin/python" ]]; then
    printf '%s\n' "${REPO_ROOT}/.venv-lexicon/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  die "No Python interpreter found for lexicon suite"
}

run_full_suite() {
  print_section "Full lexicon suite"
  if [[ -x "${REPO_ROOT}/.venv-lexicon/bin/python" && -x "${REPO_ROOT}/.venv-backend/bin/python" ]]; then
    make test-lexicon
  else
    make ci-test-lexicon
  fi
}

run_smoke_suite() {
  local py
  local smoke_dir
  local validate_output
  local validate_json
  local compiled_validate_output
  local compiled_validate_json
  py="$(lexicon_python)"
  smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/lexicon-smoke.XXXXXX")"
  cleanup_smoke() {
    rm -rf "${smoke_dir}"
  }
  trap cleanup_smoke EXIT

  print_section "Lexicon smoke flow"
  mkdir -p "${smoke_dir}"
  LEXICON_SKIP_VENV_GUARD=1 "${py}" -m tools.lexicon.cli build-base --rerun-existing run set lead --output-dir "${smoke_dir}"
  test -f "${smoke_dir}/lexemes.jsonl"
  LEXICON_SKIP_VENV_GUARD=1 "${py}" -m tools.lexicon.cli enrich --snapshot-dir "${smoke_dir}" --provider-mode placeholder
  validate_output="$(
    LEXICON_SKIP_VENV_GUARD=1 "${py}" -m tools.lexicon.cli validate --snapshot-dir "${smoke_dir}"
  )"
  printf '%s\n' "${validate_output}"
  validate_json="$(printf '%s\n' "${validate_output}" | tail -n 1)"
  "${py}" - "${validate_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["error_count"] == 0, payload
PY
  test -f "${smoke_dir}/words.enriched.jsonl"
  compiled_validate_output="$(
    LEXICON_SKIP_VENV_GUARD=1 "${py}" -m tools.lexicon.cli validate --compiled-input "${smoke_dir}/words.enriched.jsonl"
  )"
  printf '%s\n' "${compiled_validate_output}"
  compiled_validate_json="$(printf '%s\n' "${compiled_validate_output}" | tail -n 1)"
  "${py}" - "${compiled_validate_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["error_count"] == 0, payload
PY
  "${py}" - <<'PY' "${smoke_dir}/words.enriched.jsonl"
import json
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
assert rows, "expected at least one compiled word row"
phonetics = rows[0]["phonetics"]
assert set(phonetics.keys()) == {"us", "uk", "au"}
assert all(isinstance(phonetics[accent]["ipa"], str) and phonetics[accent]["ipa"] for accent in ("us", "uk", "au"))
PY
  trap - EXIT
  cleanup_smoke
}

case "${suite}" in
  full)
    run_logged "${label}" "full.log" run_full_suite
    ;;
  smoke)
    run_logged "${label}" "smoke.log" run_smoke_suite
    ;;
  gate)
    run_logged "${label}" "full.log" run_full_suite
    run_logged "${label}" "smoke.log" run_smoke_suite
    ;;
  *)
    die "Unknown lexicon suite '${suite}'. Use full|smoke|gate."
    ;;
esac
