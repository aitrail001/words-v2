#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:?usage: scripts/db/refresh-template-from-db.sh <env-file> <source-db> <target-template-db>}"
SOURCE_DB="${2:?usage: scripts/db/refresh-template-from-db.sh <env-file> <source-db> <target-template-db>}"
TARGET_TEMPLATE_DB="${3:?usage: scripts/db/refresh-template-from-db.sh <env-file> <source-db> <target-template-db>}"

TMP_DUMP="$(mktemp -t words-db-XXXXXX.dump)"
trap 'rm -f "$TMP_DUMP"' EXIT

./scripts/db/backup-db.sh "$ENV_FILE" "$SOURCE_DB" "$TMP_DUMP"
./scripts/db/restore-db-from-dump.sh "$ENV_FILE" "$TARGET_TEMPLATE_DB" "$TMP_DUMP"

echo "[db] refreshed template $TARGET_TEMPLATE_DB from $SOURCE_DB"
