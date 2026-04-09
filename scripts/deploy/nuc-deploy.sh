#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.stack.nuc}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-words-stack}"

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" -f compose.infra.yml up -d

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" \
  -f compose.infra.yml -f compose.teststack.yml up -d --build --remove-orphans

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" \
  -f compose.infra.yml -f compose.teststack.yml \
  exec -T backend curl -fsS http://localhost:8000/api/health >/dev/null

docker compose -p "$PROJECT_NAME" --env-file "$ENV_FILE" \
  -f compose.infra.yml -f compose.teststack.yml -f compose.e2e.yml \
  --profile tests run --rm playwright npm run test:smoke:ci
