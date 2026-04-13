#!/usr/bin/env bash
set -euo pipefail

CI_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${CI_SCRIPT_DIR}/../.." && pwd)"

ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env.stack.gate}"
PR_INFRA_COMPOSE_FILE="${PR_INFRA_COMPOSE_FILE:-compose.infra.gate.yml}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-words-gate-stack}"
LOG_ROOT="${LOG_ROOT:-${REPO_ROOT}/artifacts/ci-gate}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

print_section() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

cd_repo_root() {
  cd "${REPO_ROOT}"
}

ensure_env_file() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    die "Expected ${ENV_FILE}. Copy .env.stack.gate.example to .env.stack.gate first."
  fi
}

load_env() {
  ensure_env_file
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME}"
  export WORDS_DATA_DIR="${WORDS_DATA_DIR:-${REPO_ROOT}/data}"
  mkdir -p "${WORDS_DATA_DIR}" "${LOG_ROOT}"
}

artifact_dir() {
  local label="$1"
  local out_dir="${LOG_ROOT}/${label}"
  mkdir -p "${out_dir}"
  printf '%s\n' "${out_dir}"
}

artifact_path() {
  local label="$1"
  local file_name="$2"
  printf '%s/%s\n' "$(artifact_dir "${label}")" "${file_name}"
}

format_command_line() {
  local arg
  printf '$'
  for arg in "$@"; do
    printf ' %q' "${arg}"
  done
  printf '\n'
}

ensure_nonempty_log() {
  local file="$1"
  local fallback_message="$2"
  if [[ ! -s "${file}" ]]; then
    printf '%s\n' "${fallback_message}" >"${file}"
  fi
}

capture_command_output() {
  local file="$1"
  shift
  local status=0

  {
    format_command_line "$@"
    "$@"
  } >"${file}" 2>&1 || status=$?

  if (( status != 0 )); then
    printf '\n[ci-gate] command exited with status %s\n' "${status}" >>"${file}"
  fi

  ensure_nonempty_log "${file}" "[ci-gate] command produced no output"
  return "${status}"
}

run_logged() {
  local label="$1"
  local log_name="$2"
  shift 2

  local out_dir
  local file
  out_dir="$(artifact_dir "${label}")"
  file="${out_dir}/${log_name}"

  local status=0
  (
    set -o pipefail
    {
      format_command_line "$@"
      "$@"
    } 2>&1 | tee "${file}"
  ) || status=$?

  if (( status != 0 )); then
    printf '\n[ci-gate] command exited with status %s\n' "${status}" >>"${file}"
  fi

  ensure_nonempty_log "${file}" "[ci-gate] command produced no output"
  return "${status}"
}

init_gate_artifacts() {
  local gate_label="$1"
  local out_dir
  out_dir="$(artifact_dir "${gate_label}")"

  : >"${out_dir}/steps.log"
  {
    printf 'gate=%s\n' "${gate_label}"
    printf 'started_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'log_root=%s\n' "${LOG_ROOT}"
  } >"${out_dir}/summary.log"
}

record_gate_step() {
  local gate_label="$1"
  local step_name="$2"
  local suite_label="${3:-}"
  local out_dir
  out_dir="$(artifact_dir "${gate_label}")"

  if [[ -n "${suite_label}" ]]; then
    printf '[%s] %s -> artifacts/ci-gate/%s\n' \
      "$(date '+%H:%M:%S')" "${step_name}" "${suite_label}" >>"${out_dir}/steps.log"
  else
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "${step_name}" >>"${out_dir}/steps.log"
  fi
}

append_gate_summary() {
  local gate_label="$1"
  shift
  local out_dir
  out_dir="$(artifact_dir "${gate_label}")"
  printf '%s\n' "$*" >>"${out_dir}/summary.log"
}

finalize_gate_artifacts() {
  local gate_label="$1"
  local status="$2"
  append_gate_summary "${gate_label}" "status=${status}"
  append_gate_summary "${gate_label}" "finished_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}

compose_infra() {
  (
    cd "${REPO_ROOT}"
    docker compose \
      --env-file "${ENV_FILE}" \
      -p "${COMPOSE_PROJECT_NAME}" \
      -f "${PR_INFRA_COMPOSE_FILE}" \
      "$@"
  )
}

compose_stack() {
  (
    cd "${REPO_ROOT}"
    docker compose \
      --env-file "${ENV_FILE}" \
      -p "${COMPOSE_PROJECT_NAME}" \
      -f "${PR_INFRA_COMPOSE_FILE}" \
      -f compose.teststack.yml \
      "$@"
  )
}

compose_e2e() {
  (
    cd "${REPO_ROOT}"
    docker compose \
      --env-file "${ENV_FILE}" \
      -p "${COMPOSE_PROJECT_NAME}" \
      -f "${PR_INFRA_COMPOSE_FILE}" \
      -f compose.teststack.yml \
      -f compose.e2e.yml \
      "$@"
  )
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-60}"
  local sleep_secs="${4:-2}"

  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${sleep_secs}"
  done

  die "${name} did not become ready at ${url}"
}

wait_for_infra() {
  local attempts="${1:-60}"

  for _ in $(seq 1 "${attempts}"); do
    if compose_infra exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${TEST_DB_NAME}" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  compose_infra exec -T postgres pg_isready -U "${POSTGRES_USER}" -d "${TEST_DB_NAME}" >/dev/null 2>&1 \
    || die "Postgres did not become ready"

  for _ in $(seq 1 "${attempts}"); do
    if compose_infra exec -T redis redis-cli ping >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  compose_infra exec -T redis redis-cli ping >/dev/null 2>&1 \
    || die "Redis did not become ready"
}

wait_for_stack() {
  wait_for_http "backend" "http://localhost:${TEST_BACKEND_PORT:-18000}/api/health"
  wait_for_http "frontend" "http://localhost:${TEST_PUBLIC_PORT:-13000}/register"
  wait_for_http "admin frontend" "http://localhost:${TEST_ADMIN_PORT:-13001}/login"
}

start_infra() {
  local label="${1:-infra-start}"
  local out_dir
  out_dir="$(artifact_dir "${label}")"

  print_section "Starting disposable postgres/redis"
  if ! capture_command_output "${out_dir}/compose-up.log" compose_infra up -d postgres redis; then
    capture_command_output "${out_dir}/compose-ps.log" compose_infra ps || true
    echo "Compose infra startup failed. See ${out_dir}/compose-up.log" >&2
    return 1
  fi
  capture_command_output "${out_dir}/compose-ps.log" compose_infra ps || true
  wait_for_infra
}

start_stack() {
  local label="${1:-stack-start}"
  local out_dir
  out_dir="$(artifact_dir "${label}")"

  print_section "Starting disposable full app stack"
  if ! capture_command_output "${out_dir}/compose-up.log" compose_stack up -d --build --force-recreate postgres redis backend worker frontend admin-frontend nginx; then
    capture_command_output "${out_dir}/compose-ps.log" compose_stack ps || true
    echo "Compose stack startup failed. See ${out_dir}/compose-up.log" >&2
    return 1
  fi

  capture_command_output "${out_dir}/compose-ps.log" compose_stack ps || true
  wait_for_stack
}

apply_migrations() {
  local label="${1:-stack-migrations}"
  local out_dir
  out_dir="$(artifact_dir "${label}")"

  print_section "Applying backend migrations"
  capture_command_output "${out_dir}/migrations.log" compose_stack exec -T backend alembic upgrade head
}

collect_infra_logs() {
  local label="$1"
  local out_dir
  out_dir="$(artifact_dir "${label}")"
  capture_command_output "${out_dir}/compose-ps.log" compose_infra ps || true
  capture_command_output "${out_dir}/postgres.log" compose_infra logs --tail=400 postgres || true
  capture_command_output "${out_dir}/redis.log" compose_infra logs --tail=400 redis || true
}

collect_stack_logs() {
  local label="$1"
  local out_dir
  out_dir="$(artifact_dir "${label}")"
  capture_command_output "${out_dir}/compose-ps.log" compose_stack ps || true
  capture_command_output "${out_dir}/postgres.log" compose_stack logs --tail=400 postgres || true
  capture_command_output "${out_dir}/redis.log" compose_stack logs --tail=400 redis || true
  capture_command_output "${out_dir}/backend.log" compose_stack logs --tail=400 backend || true
  capture_command_output "${out_dir}/worker.log" compose_stack logs --tail=400 worker || true
  capture_command_output "${out_dir}/frontend.log" compose_stack logs --tail=400 frontend || true
  capture_command_output "${out_dir}/admin-frontend.log" compose_stack logs --tail=400 admin-frontend || true
  capture_command_output "${out_dir}/nginx.log" compose_stack logs --tail=400 nginx || true
}

teardown_infra() {
  print_section "Tearing down disposable infra"
  if ! compose_infra down -v --remove-orphans; then
    echo "WARN: disposable infra teardown failed" >&2
  fi
}

teardown_stack() {
  print_section "Tearing down disposable full app stack"
  if ! compose_e2e down -v --remove-orphans; then
    echo "WARN: disposable full app stack teardown failed" >&2
  fi
}

run_backend_pytest() {
  (
    cd "${REPO_ROOT}"
    # shellcheck disable=SC1091
    source .venv-backend/bin/activate
    export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-55432}/${TEST_DB_NAME}"
    export DATABASE_URL_SYNC="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_PORT:-55432}/${TEST_DB_NAME}"
    export REDIS_URL="redis://localhost:${REDIS_PORT:-56379}"
    export ENVIRONMENT="test"
    export JWT_SECRET="${JWT_SECRET:-test-secret}"
    cd backend
    pytest -q "$@"
  )
}

run_playwright_script() {
  local label="$1"
  local npm_script="$2"
  run_logged "${label}" "playwright.log" compose_e2e --profile tests run --rm --no-deps \
    -e E2E_BASE_URL="http://frontend:3000" \
    -e E2E_API_URL="http://backend:8000/api" \
    -e E2E_ADMIN_URL="http://admin-frontend:3001" \
    -e E2E_DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${TEST_DB_NAME}" \
    playwright npm run "${npm_script}"
}
