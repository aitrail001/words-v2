#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:?usage: scripts/db/restore-db-from-dump.sh <env-file> <target-db> <dump-file>}"
TARGET_DB="${2:?usage: scripts/db/restore-db-from-dump.sh <env-file> <target-db> <dump-file>}"
DUMP_FILE="${3:?usage: scripts/db/restore-db-from-dump.sh <env-file> <target-db> <dump-file>}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -f "$DUMP_FILE" ]]; then
  echo "Dump file not found: $DUMP_FILE" >&2
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

compose exec -T postgres psql -U "$POSTGRES_USER" -d "${PG_BOOT_DB:-postgres}" -v ON_ERROR_STOP=1 -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TARGET_DB}' AND pid <> pg_backend_pid();"

compose exec -T postgres dropdb -U "$POSTGRES_USER" --if-exists "$TARGET_DB"
compose exec -T postgres createdb -U "$POSTGRES_USER" -T template0 "$TARGET_DB"

cat "$DUMP_FILE" | compose exec -T postgres sh -lc \
  "pg_restore -U \"$POSTGRES_USER\" -d \"$TARGET_DB\" --no-owner --no-privileges"

echo "[db] restored $TARGET_DB from $DUMP_FILE"
