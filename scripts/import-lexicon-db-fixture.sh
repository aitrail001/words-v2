#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
FIXTURE_NAME="${1:-smoke}"

case "${FIXTURE_NAME}" in
  smoke)
    FIXTURE_PATH="/app/tests/fixtures/lexicon-db/smoke/approved.jsonl"
    ;;
  full)
    FIXTURE_PATH="/app/tests/fixtures/lexicon-db/full/approved.jsonl"
    ;;
  *)
    echo "usage: $0 [smoke|full]" >&2
    exit 2
    ;;
esac

if [[ ! -f "${ROOT_DIR}${FIXTURE_PATH#/app}" ]]; then
  echo "[lexicon-fixtures] fixture not found: ${ROOT_DIR}${FIXTURE_PATH#/app}" >&2
  exit 1
fi

echo "[lexicon-fixtures] running backend migrations"
docker compose -f "${COMPOSE_FILE}" exec -T backend alembic upgrade head

echo "[lexicon-fixtures] importing ${FIXTURE_NAME} fixture from ${FIXTURE_PATH}"
docker compose -f "${COMPOSE_FILE}" exec -T backend sh -lc \
  "cd /app && python -m tools.lexicon.cli import-db --input '${FIXTURE_PATH}' --source-type repo_fixture --source-reference '${FIXTURE_NAME}-fixture' --log-file /tmp/import-db-${FIXTURE_NAME}.log --log-level quiet"
