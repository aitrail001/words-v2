#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.stack.mac}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

TEMPLATE_DB="${2:-$TEST_TEMPLATE_DB_NAME}"
RUN_DB_NAME="${3:-vocabapp_test_run_$(date +%Y%m%d_%H%M%S)}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-words-stack}"

compose() {
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f compose.infra.yml "$@"
}

compose exec -T postgres psql -U "$POSTGRES_USER" -d "${PG_BOOT_DB:-postgres}" -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TEMPLATE_DB}' AND pid <> pg_backend_pid();"

compose exec -T postgres createdb -U "$POSTGRES_USER" -T "$TEMPLATE_DB" "$RUN_DB_NAME"

echo "$RUN_DB_NAME"
