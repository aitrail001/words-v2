#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:?usage: scripts/db/backup-db.sh <env-file> <source-db> <output-file>}"
SOURCE_DB="${2:?usage: scripts/db/backup-db.sh <env-file> <source-db> <output-file>}"
OUTPUT_FILE="${3:?usage: scripts/db/backup-db.sh <env-file> <source-db> <output-file>}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_FILE")"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-words-stack}"

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f compose.infra.yml \
  exec -T postgres sh -lc "pg_dump -U \"$POSTGRES_USER\" -d \"$SOURCE_DB\" -Fc" > "$OUTPUT_FILE"

echo "[db] wrote $OUTPUT_FILE from $SOURCE_DB"
