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

print_note() {
  local message="$1"
  if [[ -t 1 ]]; then
    printf '\033[1;36m%s\033[0m\n' "${message}"
  else
    printf '%s\n' "${message}"
  fi
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

compose_infra_with() {
  local env_file="$1"
  local project_name="$2"
  shift 2
  (
    cd "${REPO_ROOT}"
    env \
      -u COMPOSE_PROJECT_NAME \
      -u POSTGRES_USER \
      -u POSTGRES_PASSWORD \
      -u TEST_DB_NAME \
      -u POSTGRES_PORT \
      -u REDIS_PORT \
      docker compose \
      --env-file "${env_file}" \
      -p "${project_name}" \
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

start_gate_postgres_instance() {
  local project_name="$1"
  local requested_port="$2"
  local db_name="$3"
  local user="${4:-vocabapp}"
  local password="${5:-devpassword}"
  local env_file
  local attempts=60
  local mapped_host=""
  local mapped_port=""

  env_file="$(mktemp "${TMPDIR:-/tmp}/gate-postgres-env.XXXXXX")"
  cat >"${env_file}" <<EOF
COMPOSE_PROJECT_NAME=${project_name}
POSTGRES_USER=${user}
POSTGRES_PASSWORD=${password}
TEST_DB_NAME=${db_name}
POSTGRES_PORT=${requested_port}
REDIS_PORT=0
EOF

  if ! compose_infra_with "${env_file}" "${project_name}" up -d postgres >/dev/null; then
    rm -f "${env_file}"
    return 1
  fi

  for _ in $(seq 1 "${attempts}"); do
    if compose_infra_with "${env_file}" "${project_name}" exec -T postgres pg_isready -U "${user}" -d "${db_name}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ! mapped_host="$(compose_infra_with "${env_file}" "${project_name}" port postgres 5432 2>/dev/null | tail -n 1)"; then
    mapped_host=""
  fi

  if [[ "${mapped_host}" == *:* ]]; then
    mapped_port="${mapped_host##*:}"
  fi

  if [[ -z "${mapped_port}" ]]; then
    compose_infra_with "${env_file}" "${project_name}" ps >&2 || true
    compose_infra_with "${env_file}" "${project_name}" logs --tail=200 postgres >&2 || true
    compose_infra_with "${env_file}" "${project_name}" down -v --remove-orphans >/dev/null || true
    rm -f "${env_file}"
    return 1
  fi

  for _ in $(seq 1 "${attempts}"); do
    if nc -z 127.0.0.1 "${mapped_port}" >/dev/null 2>&1; then
      rm -f "${env_file}"
      printf '{"project":"%s","database_url":"postgresql://%s:%s@127.0.0.1:%s/%s"}\n' \
        "${project_name}" "${user}" "${password}" "${mapped_port}" "${db_name}"
      return 0
    fi
    sleep 1
  done

  compose_infra_with "${env_file}" "${project_name}" ps >&2 || true
  compose_infra_with "${env_file}" "${project_name}" logs --tail=200 postgres >&2 || true
  compose_infra_with "${env_file}" "${project_name}" down -v --remove-orphans >/dev/null || true

  rm -f "${env_file}"
  return 1
}

stop_gate_postgres_instance() {
  local project_name="$1"
  local env_file

  env_file="$(mktemp "${TMPDIR:-/tmp}/gate-postgres-env.XXXXXX")"
  cat >"${env_file}" <<EOF
COMPOSE_PROJECT_NAME=${project_name}
EOF

  compose_infra_with "${env_file}" "${project_name}" down -v --remove-orphans >/dev/null || true
  rm -f "${env_file}"
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
  local suite_dir
  local html_dir
  local results_dir
  local junit_file
  local container_html_dir
  local container_results_dir
  local container_junit_file

  suite_dir="$(artifact_dir "${label}")/playwright"
  html_dir="${suite_dir}/html-report"
  results_dir="${suite_dir}/test-results"
  junit_file="${suite_dir}/results.xml"
  container_html_dir="/workspace/artifacts/ci-gate/${label}/playwright/html-report"
  container_results_dir="/workspace/artifacts/ci-gate/${label}/playwright/test-results"
  container_junit_file="/workspace/artifacts/ci-gate/${label}/playwright/results.xml"

  mkdir -p "${html_dir}" "${results_dir}"

  run_logged "${label}" "playwright.log" compose_e2e --profile tests run --rm --no-deps \
    -e E2E_BASE_URL="http://frontend:3000" \
    -e E2E_API_URL="http://backend:8000/api" \
    -e E2E_ADMIN_URL="http://admin-frontend:3001" \
    -e E2E_DB_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${TEST_DB_NAME}" \
    -e PLAYWRIGHT_HTML_OUTPUT_DIR="${container_html_dir}" \
    -e PLAYWRIGHT_RESULTS_DIR="${container_results_dir}" \
    -e PLAYWRIGHT_JUNIT_OUTPUT_FILE="${container_junit_file}" \
    playwright npm run "${npm_script}"

  print_section "Playwright HTML report: ${html_dir}/index.html"
  print_note "Open with: make open-e2e-report E2E_REPORT_DIR=artifacts/ci-gate/${label}/playwright/html-report"
  print_note "Show with: make show-e2e-report E2E_REPORT_DIR=artifacts/ci-gate/${label}/playwright/html-report"
}
