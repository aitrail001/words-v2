#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_ROOT="${ROOT_DIR}/benchmarks/results"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULTS_DIR="${RESULTS_ROOT}/${TIMESTAMP}"
mkdir -p "${RESULTS_DIR}"

COMPOSE_CMD=(docker compose -f "${ROOT_DIR}/docker-compose.prod.yml")
HOST_BASE_URL="${HOST_BASE_URL:-http://localhost:8088/api}"
K6_BASE_URL="${K6_BASE_URL:-http://host.docker.internal:8088/api}"
BENCH_USER_EMAIL="${BENCH_USER_EMAIL:-bench-user@example.com}"
BENCH_USER_PASSWORD="${BENCH_USER_PASSWORD:-BenchPass123!}"
BENCH_ADMIN_EMAIL="${BENCH_ADMIN_EMAIL:-bench-admin@example.com}"
BENCH_ADMIN_PASSWORD="${BENCH_ADMIN_PASSWORD:-BenchPass123!}"
K6_IMAGE="${K6_IMAGE:-grafana/k6:0.50.0}"
STAGES_STR="${BENCHMARK_VUS:-1 5 10 25 50 100}"
DURATION="${BENCHMARK_DURATION:-45s}"
HOST_BUDGET="${HOST_BUDGET:-4 vCPU / 16 GB RAM}"

register_or_login() {
  local email="$1"
  local password="$2"

  local register_response
  register_response="$(curl -s -o /tmp/bench-auth-body.$$ -w '%{http_code}' -X POST "${HOST_BASE_URL}/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${password}\"}")"

  if [[ "${register_response}" != "201" && "${register_response}" != "409" ]]; then
    echo "unexpected auth response for ${email}: ${register_response}" >&2
    cat /tmp/bench-auth-body.$$ >&2 || true
    exit 1
  fi

  curl -s -X POST "${HOST_BASE_URL}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${password}\"}"
}

extract_json_field() {
  local field="$1"
  python3 -c 'import json,sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$field"
}

psql_value() {
  local sql="$1"
  "${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" -Atqc "$sql"
}

echo "Seeding benchmark users and fixture ids into ${RESULTS_DIR}"

USER_TOKENS="$(register_or_login "${BENCH_USER_EMAIL}" "${BENCH_USER_PASSWORD}")"
ADMIN_TOKENS="$(register_or_login "${BENCH_ADMIN_EMAIL}" "${BENCH_ADMIN_PASSWORD}")"

ADMIN_USER_ID="$(psql_value "select id::text from users where email = '${BENCH_ADMIN_EMAIL}' limit 1;")"
"${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" \
  -c "update users set role = 'admin', is_active = true, updated_at = now() where id = '${ADMIN_USER_ID}'::uuid;" >/dev/null

ADMIN_TOKENS="$(register_or_login "${BENCH_ADMIN_EMAIL}" "${BENCH_ADMIN_PASSWORD}")"

BENCH_USER_ACCESS_TOKEN="$(printf '%s' "${USER_TOKENS}" | extract_json_field access_token)"
BENCH_ADMIN_ACCESS_TOKEN="$(printf '%s' "${ADMIN_TOKENS}" | extract_json_field access_token)"

BENCH_WORD_ID="$(psql_value "select id::text from lexicon.words where language = 'en' order by word asc limit 1;")"
BENCH_PHRASE_ID="$(psql_value "select id::text from lexicon.phrase_entries order by phrase_text asc limit 1;")"
BENCH_MEANING_IDS="$(psql_value "select string_agg(id::text, ',') from (select id from lexicon.meanings order by created_at asc limit 25) t;")"

"${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" \
  -c "create extension if not exists pg_stat_statements;" >/dev/null
"${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" \
  -c "select pg_stat_statements_reset();" >/dev/null

cat > "${RESULTS_DIR}/seed.json" <<EOF
{
  "host_base_url": "${HOST_BASE_URL}",
  "k6_base_url": "${K6_BASE_URL}",
  "bench_user_email": "${BENCH_USER_EMAIL}",
  "bench_admin_email": "${BENCH_ADMIN_EMAIL}",
  "bench_word_id": "${BENCH_WORD_ID}",
  "bench_phrase_id": "${BENCH_PHRASE_ID}",
  "bench_meaning_ids": "${BENCH_MEANING_IDS}"
}
EOF

for vus in ${(z)STAGES_STR}; do
  stage_dir="${RESULTS_DIR}/vus-${vus}"
  mkdir -p "${stage_dir}"
  echo "Running benchmark stage: ${vus} VUs for ${DURATION}"

  "${ROOT_DIR}/scripts/benchmark/capture-docker-stats.sh" "${stage_dir}/docker-stats.csv" 2 &
  stats_pid=$!

  stage_exit_code=0
  docker run --rm \
    -v "${ROOT_DIR}:/work" \
    -w /work \
    -e BASE_URL="${K6_BASE_URL}" \
    -e BENCH_USER_EMAIL="${BENCH_USER_EMAIL}" \
    -e BENCH_USER_PASSWORD="${BENCH_USER_PASSWORD}" \
    -e BENCH_ADMIN_EMAIL="${BENCH_ADMIN_EMAIL}" \
    -e BENCH_ADMIN_PASSWORD="${BENCH_ADMIN_PASSWORD}" \
    -e BENCH_WORD_ID="${BENCH_WORD_ID}" \
    -e BENCH_PHRASE_ID="${BENCH_PHRASE_ID}" \
    -e BENCH_MEANING_IDS="${BENCH_MEANING_IDS}" \
    -e K6_SUMMARY_PATH="/work/${stage_dir#${ROOT_DIR}/}/k6-summary.json" \
    "${K6_IMAGE}" run \
    --vus "${vus}" \
    --duration "${DURATION}" \
    benchmarks/k6/main.js | tee "${stage_dir}/k6-output.txt" || stage_exit_code=$?

  printf '%s\n' "${stage_exit_code}" > "${stage_dir}/k6-exit-code.txt"

  kill "${stats_pid}" >/dev/null 2>&1 || true
  wait "${stats_pid}" 2>/dev/null || true
done

"${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" \
  -c "\\copy (select calls, round(total_exec_time::numeric, 2) as total_exec_time_ms, round(mean_exec_time::numeric, 2) as mean_exec_time_ms, rows, regexp_replace(query, '[[:space:]]+', ' ', 'g') as query from pg_stat_statements where dbid = (select oid from pg_database where datname = current_database()) order by total_exec_time desc limit 15) to stdout with csv header" \
  > "${RESULTS_DIR}/pg-stat-statements-top-total.csv"

"${COMPOSE_CMD[@]}" exec -T postgres psql -U "${POSTGRES_USER:-vocabapp}" -d "${POSTGRES_DB:-vocabapp_dev}" \
  -c "\\copy (select calls, round(total_exec_time::numeric, 2) as total_exec_time_ms, round(mean_exec_time::numeric, 2) as mean_exec_time_ms, rows, regexp_replace(query, '[[:space:]]+', ' ', 'g') as query from pg_stat_statements where dbid = (select oid from pg_database where datname = current_database()) and calls >= 5 order by mean_exec_time desc limit 15) to stdout with csv header" \
  > "${RESULTS_DIR}/pg-stat-statements-top-mean.csv"

python3 "${ROOT_DIR}/scripts/benchmark/render-capacity-report.py" \
  "${RESULTS_DIR}" \
  "${ROOT_DIR}/docs/reports/2026-03-27-single-host-capacity-report.md" \
  "${HOST_BUDGET}"

echo "Benchmark results written to ${RESULTS_DIR}"
echo "Capacity report written to ${ROOT_DIR}/docs/reports/2026-03-27-single-host-capacity-report.md"
