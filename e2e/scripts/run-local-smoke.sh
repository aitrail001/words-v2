#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  env_postgres_user="$(grep -E '^POSTGRES_USER=' "${ROOT_DIR}/.env" | tail -n1 | cut -d'=' -f2- || true)"
  env_postgres_password="$(grep -E '^POSTGRES_PASSWORD=' "${ROOT_DIR}/.env" | tail -n1 | cut -d'=' -f2- || true)"
  env_postgres_db="$(grep -E '^POSTGRES_DB=' "${ROOT_DIR}/.env" | tail -n1 | cut -d'=' -f2- || true)"
fi

export E2E_BASE_URL="${E2E_BASE_URL:-http://frontend:3000}"
export E2E_API_URL="${E2E_API_URL:-http://backend:8000/api}"
export POSTGRES_USER="${POSTGRES_USER:-${env_postgres_user:-vocabapp}}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${env_postgres_password:-devpassword}}"
export POSTGRES_DB="${POSTGRES_DB:-${env_postgres_db:-vocabapp_dev}}"
export E2E_DB_URL="${E2E_DB_URL:-postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://backend:8000/api}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://localhost:3000,http://localhost:3001,http://frontend:3000}"

E2E_SMOKE_CLEANUP="${E2E_SMOKE_CLEANUP:-0}"

compose() {
  docker compose -f "${COMPOSE_FILE}" --profile tests "$@"
}

cleanup() {
  if [[ "${E2E_SMOKE_CLEANUP}" == "1" ]]; then
    echo "[local-smoke] cleanup enabled; stopping compose stack"
    compose down --remove-orphans
  else
    echo "[local-smoke] cleanup disabled; set E2E_SMOKE_CLEANUP=1 to tear down automatically"
  fi
}

wait_http_ready() {
  local name="$1"
  local url="$2"
  local max_attempts="${3:-60}"
  local sleep_seconds="${4:-2}"

  echo "[local-smoke] waiting for ${name}: ${url}"
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "[local-smoke] ${name} is ready"
      return 0
    fi
    sleep "${sleep_seconds}"
  done

  echo "[local-smoke] timed out waiting for ${name}: ${url}" >&2
  return 1
}

trap cleanup EXIT

echo "[local-smoke] starting compose services for tests"
compose up -d postgres redis backend frontend worker playwright

wait_http_ready "backend" "http://localhost:8000/api/health"
wait_http_ready "frontend" "http://localhost:3000"

echo "[local-smoke] running backend migrations"
compose exec -T backend alembic upgrade head

echo "[local-smoke] running playwright smoke suite"
compose exec -T playwright sh -lc "
  if [ ! -d node_modules ]; then
    npm ci --prefer-offline --no-audit --no-fund
  fi
  E2E_BASE_URL='${E2E_BASE_URL}' E2E_API_URL='${E2E_API_URL}' E2E_DB_URL='${E2E_DB_URL}' npm run test:smoke:ci
"
