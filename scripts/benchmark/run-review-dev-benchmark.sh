#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_ROOT="${ROOT_DIR}/benchmarks/results"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RESULTS_DIR="${RESULTS_ROOT}/${TIMESTAMP}"
mkdir -p "${RESULTS_DIR}"

COMPOSE_CMD=(docker compose -f "${ROOT_DIR}/docker-compose.yml" -f "${ROOT_DIR}/docker-compose.review-isolated.yml")
HOST_BASE_URL="${HOST_BASE_URL:-http://127.0.0.1:4200/api}"
K6_BASE_URL="${K6_BASE_URL:-http://host.docker.internal:4200/api}"
BENCH_USER_EMAIL="${BENCH_USER_EMAIL:-review-bench@example.com}"
BENCH_USER_PASSWORD="${BENCH_USER_PASSWORD:-BenchPass123!}"
K6_IMAGE="${K6_IMAGE:-grafana/k6:0.50.0}"
STAGES_STR="${BENCHMARK_VUS:-2 5 10 15 20 25 30 35 40 45 50}"
DURATION="${BENCHMARK_DURATION:-20s}"
HOST_BUDGET="${HOST_BUDGET:-Isolated dev stack (backend+frontend+postgres+redis on local Docker)}"
SEED_COUNT="${BENCHMARK_SEED_COUNT:-2000}"
REPORT_PATH="${REPORT_PATH:-${ROOT_DIR}/docs/reports/2026-04-02-review-dev-capacity-report.md}"

register_or_login() {
  local email="$1"
  local password="$2"

  local register_response
  register_response="$(curl -s -o /tmp/review-bench-auth-body.$$ -w '%{http_code}' -X POST "${HOST_BASE_URL}/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"${email}\",\"password\":\"${password}\"}")"

  if [[ "${register_response}" != "201" && "${register_response}" != "409" ]]; then
    echo "unexpected auth response for ${email}: ${register_response}" >&2
    cat /tmp/review-bench-auth-body.$$ >&2 || true
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

psql_exec() {
  local sql="$1"
  "${COMPOSE_CMD[@]}" exec -T postgres psql -U vocabapp -d vocabapp_dev -v ON_ERROR_STOP=1 -c "$sql" >/dev/null
}

psql_try_exec() {
  local sql="$1"
  "${COMPOSE_CMD[@]}" exec -T postgres psql -U vocabapp -d vocabapp_dev -v ON_ERROR_STOP=1 -c "$sql" >/dev/null 2>&1
}

psql_value() {
  local sql="$1"
  "${COMPOSE_CMD[@]}" exec -T postgres psql -U vocabapp -d vocabapp_dev -Atqc "$sql"
}

seed_benchmark_vocabulary() {
  psql_exec "
    delete from lexicon.meaning_examples
    where meaning_id in (
      select id from lexicon.meanings where source = 'review-benchmark'
    );
  "
  psql_exec "delete from lexicon.meanings where source = 'review-benchmark';"
  psql_exec "
    delete from lexicon.word_part_of_speech
    where word_id in (
      select id from lexicon.words where word like 'reviewbench_%'
    );
  "
  psql_exec "delete from lexicon.words where word like 'reviewbench_%';"
  psql_exec "
    with generated as (
      select
        gs as n,
        format('reviewbench_%s', lpad(gs::text, 5, '0')) as word,
        format('Benchmark definition %s', gs) as definition,
        format('The reviewbench_%s example supports review prompts.', lpad(gs::text, 5, '0')) as example_sentence
      from generate_series(1, ${SEED_COUNT}) as gs
    ),
    inserted_words as (
      insert into lexicon.words (id, word, language, phonetic, frequency_rank, created_at)
      select gen_random_uuid(), generated.word, 'en', null, 100000 + generated.n, now()
      from generated
      returning id, word
    ),
    inserted_pos as (
      insert into lexicon.word_part_of_speech (id, word_id, value, order_index, created_at)
      select gen_random_uuid(), inserted_words.id, 'noun', 0, now()
      from inserted_words
      returning word_id
    ),
    inserted_meanings as (
      insert into lexicon.meanings (
        id,
        word_id,
        definition,
        part_of_speech,
        example_sentence,
        order_index,
        source,
        created_at
      )
      select
        gen_random_uuid(),
        inserted_words.id,
        generated.definition,
        'noun',
        generated.example_sentence,
        0,
        'review-benchmark',
        now()
      from inserted_words
      join generated on generated.word = inserted_words.word
      returning id, word_id
    )
    insert into lexicon.meaning_examples (id, meaning_id, sentence, difficulty, order_index, created_at)
    select
      gen_random_uuid(),
      inserted_meanings.id,
      generated.example_sentence,
      'B1',
      0,
      now()
    from inserted_meanings
    join inserted_words on inserted_words.id = inserted_meanings.word_id
    join generated on generated.word = inserted_words.word;
  "
}

seed_review_states() {
  local user_id="$1"

  psql_exec "delete from entry_review_events where user_id = '${user_id}'::uuid;"
  psql_exec "delete from entry_review_states where user_id = '${user_id}'::uuid;"
  psql_exec "
    insert into entry_review_states (
      id,
      user_id,
      target_type,
      target_id,
      entry_type,
      entry_id,
      stability,
      difficulty,
      success_streak,
      lapse_count,
      exposure_count,
      times_remembered,
      is_fragile,
      is_suspended,
      relearning,
      recheck_due_at,
      next_due_at
    )
    select
      gen_random_uuid(),
      '${user_id}'::uuid,
      'meaning',
      picked.id,
      'word',
      picked.word_id,
      0.3,
      0.5,
      0,
      0,
      0,
      0,
      false,
      false,
      false,
      null,
      null
    from lexicon.meanings picked
    join lexicon.words w on w.id = picked.word_id
    where picked.source = 'review-benchmark'
    order by w.frequency_rank asc nulls last, picked.order_index asc, picked.word_id asc
    limit ${SEED_COUNT};
  "
}

echo "Preparing review benchmark in ${RESULTS_DIR}"
"${COMPOSE_CMD[@]}" up -d postgres redis backend frontend --wait >/dev/null

USER_TOKENS="$(register_or_login "${BENCH_USER_EMAIL}" "${BENCH_USER_PASSWORD}")"
BENCH_USER_ACCESS_TOKEN="$(printf '%s' "${USER_TOKENS}" | extract_json_field access_token)"
if [[ -z "${BENCH_USER_ACCESS_TOKEN}" ]]; then
  echo "failed to obtain benchmark access token" >&2
  exit 1
fi

BENCH_USER_ID="$(psql_value "select id::text from users where email = '${BENCH_USER_EMAIL}' limit 1;")"
if [[ -z "${BENCH_USER_ID}" ]]; then
  echo "failed to resolve benchmark user id" >&2
  exit 1
fi

seed_benchmark_vocabulary
seed_review_states "${BENCH_USER_ID}"

HAS_PG_STAT_STATEMENTS=0
psql_try_exec "create extension if not exists pg_stat_statements;" || true
if psql_try_exec "select pg_stat_statements_reset();"; then
  HAS_PG_STAT_STATEMENTS=1
fi

cat > "${RESULTS_DIR}/seed.json" <<EOF
{
  "host_base_url": "${HOST_BASE_URL}",
  "k6_base_url": "${K6_BASE_URL}",
  "bench_user_email": "${BENCH_USER_EMAIL}",
  "seed_count": ${SEED_COUNT}
}
EOF

for vus in ${(z)STAGES_STR}; do
  seed_review_states "${BENCH_USER_ID}"

  stage_dir="${RESULTS_DIR}/vus-${vus}"
  mkdir -p "${stage_dir}"
  echo "Running review benchmark stage: ${vus} VUs for ${DURATION}"

  BENCHMARK_CONTAINERS="words-srs-review-postgres words-srs-review-redis words-srs-review-backend words-srs-review-frontend" \
    "${ROOT_DIR}/scripts/benchmark/capture-docker-stats.sh" "${stage_dir}/docker-stats.csv" 2 &
  stats_pid=$!

  stage_exit_code=0
  docker run --rm \
    -v "${ROOT_DIR}:/work" \
    -w /work \
    -e BASE_URL="${K6_BASE_URL}" \
    -e BENCH_USER_EMAIL="${BENCH_USER_EMAIL}" \
    -e BENCH_USER_PASSWORD="${BENCH_USER_PASSWORD}" \
    -e K6_SUMMARY_PATH="/work/${stage_dir#${ROOT_DIR}/}/k6-summary.json" \
    "${K6_IMAGE}" run \
    --vus "${vus}" \
    --duration "${DURATION}" \
    benchmarks/k6/review-dev.js | tee "${stage_dir}/k6-output.txt" || stage_exit_code=$?

  printf '%s\n' "${stage_exit_code}" > "${stage_dir}/k6-exit-code.txt"

  kill "${stats_pid}" >/dev/null 2>&1 || true
  wait "${stats_pid}" 2>/dev/null || true
done

if [[ "${HAS_PG_STAT_STATEMENTS}" -eq 1 ]]; then
  "${COMPOSE_CMD[@]}" exec -T postgres psql -U vocabapp -d vocabapp_dev \
    -c "\\copy (select calls, round(total_exec_time::numeric, 2) as total_exec_time_ms, round(mean_exec_time::numeric, 2) as mean_exec_time_ms, rows, regexp_replace(query, '[[:space:]]+', ' ', 'g') as query from pg_stat_statements where dbid = (select oid from pg_database where datname = current_database()) order by total_exec_time desc limit 15) to stdout with csv header" \
    > "${RESULTS_DIR}/pg-stat-statements-top-total.csv"

  "${COMPOSE_CMD[@]}" exec -T postgres psql -U vocabapp -d vocabapp_dev \
    -c "\\copy (select calls, round(total_exec_time::numeric, 2) as total_exec_time_ms, round(mean_exec_time::numeric, 2) as mean_exec_time_ms, rows, regexp_replace(query, '[[:space:]]+', ' ', 'g') as query from pg_stat_statements where dbid = (select oid from pg_database where datname = current_database()) and calls >= 5 order by mean_exec_time desc limit 15) to stdout with csv header" \
    > "${RESULTS_DIR}/pg-stat-statements-top-mean.csv"
fi

CAPACITY_REPORT_TITLE="Review Dev Capacity Report" \
CAPACITY_WORKLOAD_TARGET="p95 < 500ms and error rate < 5% on the isolated review workload" \
python3 "${ROOT_DIR}/scripts/benchmark/render-capacity-report.py" \
  "${RESULTS_DIR}" \
  "${REPORT_PATH}" \
  "${HOST_BUDGET}"

echo "Benchmark results written to ${RESULTS_DIR}"
echo "Capacity report written to ${REPORT_PATH}"
