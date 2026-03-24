#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

FULL_OUTPUT="/app/tests/fixtures/lexicon-db/full/approved.jsonl"
SMOKE_OUTPUT="/app/tests/fixtures/lexicon-db/smoke/approved.jsonl"
SMOKE_WORDS="${SMOKE_WORDS:-200}"
SMOKE_PHRASES="${SMOKE_PHRASES:-100}"

echo "[lexicon-fixtures] exporting full fixture -> ${FULL_OUTPUT}"
docker compose -f "${COMPOSE_FILE}" exec -T backend sh -lc \
  "cd /app && python -m tools.lexicon.cli export-db --output '${FULL_OUTPUT}' --log-file /tmp/export-db-full.log"

echo "[lexicon-fixtures] exporting smoke fixture -> ${SMOKE_OUTPUT} (${SMOKE_WORDS} words / ${SMOKE_PHRASES} phrases)"
docker compose -f "${COMPOSE_FILE}" exec -T backend sh -lc \
  "cd /app && python -m tools.lexicon.cli export-db --output '${SMOKE_OUTPUT}' --max-words '${SMOKE_WORDS}' --max-phrases '${SMOKE_PHRASES}' --log-file /tmp/export-db-smoke.log"
