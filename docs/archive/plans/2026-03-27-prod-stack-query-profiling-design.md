# Production Stack Query Profiling Design

## Goal

Add production-like DB and API profiling to the single-host prod benchmark stack so we can identify the real bottlenecks behind the current `1 VU within strict target / 5+ VUs degraded` result, then rank the next optimization work by evidence instead of intuition.

## Scope

1. Enable Postgres-side statement tracking and slow-query visibility in the prod-like stack only.
2. Replace the knowledge-map-only DB timing helper with a shared request DB metrics helper usable by auth, reviews, lexicon inspector, and knowledge-map routes.
3. Extend the benchmark/report flow so a focused rerun produces:
   - route-level request/query timing evidence
   - top SQL by total time / mean time / calls
   - Docker CPU evidence for backend and Postgres
4. Write the resulting bottleneck analysis into the capacity report and project status.

## Architecture

### 1. Postgres profiling in the prod stack

- Enable `pg_stat_statements` via Postgres startup config in `docker-compose.prod.yml`.
- Keep it isolated to the prod-like benchmark stack so dev ergonomics do not change.
- Capture a query report after benchmark execution using SQL against `pg_stat_statements`.
- Add lightweight slow-query logging settings suitable for benchmark runs.

### 2. Shared app-side DB metrics helper

- Move request DB timing/count instrumentation into a shared helper module under `backend/app/api/` or `backend/app/core/`.
- The helper should wrap `AsyncSession.execute` for the request scope and provide:
  - query count
  - summed query time in ms
  - request duration in ms
- Routes should opt in explicitly so we do not change all API behavior at once.
- Knowledge-map should switch onto the shared helper rather than keep a one-off local version.

### 3. Route coverage for the first profiling pass

Instrument these hot paths first:
- `auth`: `login`, `refresh`, `me`
- `reviews`: `queue/stats`, `queue/due`, `queue`, `queue/{id}/submit`
- `knowledge_map`: existing list/detail/overview/dashboard/search paths
- `lexicon_inspector`: list + word detail + phrase detail

Headers/logging should be route-family specific but structurally consistent so the benchmark runner can consume them later if needed.

### 4. Benchmark/report integration

- Keep the existing mixed `k6` workload and Docker stats capture.
- After the run, query `pg_stat_statements` and persist the top statements into the results directory.
- Extend the markdown report to include:
  - top SQL by total execution time
  - top SQL by mean execution time
  - summary interpretation tying likely route families to likely SQL hotspots

## Acceptance Criteria

1. Prod-like stack comes up with `pg_stat_statements` enabled.
2. Shared DB request metrics are used by knowledge-map, auth, reviews, and lexicon-inspector routes.
3. The benchmark runner emits a SQL profiling artifact alongside k6 summaries and Docker stats.
4. The generated report contains ranked SQL evidence and a concrete next-optimization list.
5. `docs/status/project-status.md` records the profiling slice and the measured findings.

## Out of Scope

- Fixing the identified slow queries in this same slice
- Adding PgBouncer
- Adding Redis caching changes
- Changing the benchmark workload mix
