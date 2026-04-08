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

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-words-stack}"

compose() {
  docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f compose.infra.yml "$@"
}

psql_postgres() {
  compose exec -T postgres psql -U "$POSTGRES_USER" -d "${PG_BOOT_DB:-postgres}" -v ON_ERROR_STOP=1 "$@"
}

db_exists() {
  psql_postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${1}'" | grep -q 1
}

create_db_if_missing() {
  local db="$1"
  if db_exists "$db"; then
    echo "[db] exists: $db"
  else
    echo "[db] creating: $db"
    compose exec -T postgres createdb -U "$POSTGRES_USER" "$db"
  fi
}

create_db_if_missing "$DEV_DB_NAME"
create_db_if_missing "$TEST_DB_NAME"
create_db_if_missing "$TEST_TEMPLATE_DB_NAME"
create_db_if_missing "$SMOKE_TEMPLATE_DB_NAME"

echo "[db] long-lived databases ready"
