#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'EOF' >&2
Usage:
  gate-postgres.sh start --project <name> [--port <port>] --db <name> [--user <user>] [--password <password>]
  gate-postgres.sh stop --project <name>
EOF
  exit 2
}

command_name="${1:-}"
shift || true

project=""
port="0"
db_name=""
user="vocabapp"
password="devpassword"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      project="${2:-}"
      shift 2
      ;;
    --port)
      port="${2:-}"
      shift 2
      ;;
    --db)
      db_name="${2:-}"
      shift 2
      ;;
    --user)
      user="${2:-}"
      shift 2
      ;;
    --password)
      password="${2:-}"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

case "${command_name}" in
  start)
    [[ -n "${project}" && -n "${db_name}" ]] || usage
    start_gate_postgres_instance "${project}" "${port}" "${db_name}" "${user}" "${password}"
    ;;
  stop)
    [[ -n "${project}" ]] || usage
    stop_gate_postgres_instance "${project}"
    ;;
  *)
    usage
    ;;
esac
