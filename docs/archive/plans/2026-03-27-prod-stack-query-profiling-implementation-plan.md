# Production Stack Query Profiling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Postgres and route-level profiling to the prod-like benchmark stack, rerun the benchmark, and produce a ranked bottleneck report.

**Architecture:** Enable `pg_stat_statements` in the prod stack, factor request-scoped DB metrics into a shared helper for the main hot route families, and extend the benchmark runner to collect SQL profiling artifacts and render them into the capacity report.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, Postgres 15, Docker Compose, k6, Python reporting scripts.

---

### Task 1: Add Postgres-side profiling to the prod stack

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `scripts/init-db.sql`
- Test: manual `SHOW shared_preload_libraries` / `SELECT * FROM pg_extension`

**Steps:**
1. Configure the prod Postgres container to preload `pg_stat_statements`.
2. Ensure the extension is created during DB initialization if absent.
3. Add slow-query-friendly logging settings for the benchmark stack.
4. Recreate the prod Postgres service and verify the extension is active.

### Task 2: Extract shared request DB metrics helper

**Files:**
- Create: `backend/app/api/request_db_metrics.py`
- Modify: `backend/app/api/knowledge_map.py`
- Test: `backend/tests/test_knowledge_map_api.py`

**Steps:**
1. Write a shared helper that instruments `AsyncSession.execute` for one request scope.
2. Port knowledge-map onto that helper without changing its header contract.
3. Keep the helper generic enough for auth/reviews/inspector routes.
4. Run focused API tests to prove knowledge-map behavior is unchanged.

### Task 3: Instrument auth, reviews, and lexicon inspector hot paths

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/reviews.py`
- Modify: `backend/app/api/lexicon_inspector.py`
- Add/Modify tests in `backend/tests/`

**Steps:**
1. Add request/response access so hot routes can emit query-count/query-time/request-time headers.
2. Use the shared helper for the selected auth, review, and inspector endpoints.
3. Add targeted tests pinning header presence and basic metric semantics.
4. Run the focused backend test subset.

### Task 4: Capture SQL profiling artifacts in the benchmark harness

**Files:**
- Modify: `scripts/benchmark/run-single-host-benchmark.sh`
- Modify: `scripts/benchmark/render-capacity-report.py`
- Possibly create: `scripts/benchmark/export-pg-stat-statements.sql`

**Steps:**
1. Reset `pg_stat_statements` before the benchmark run.
2. Export ranked SQL stats after the run into the results directory.
3. Extend the report renderer to include the top SQL findings.
4. Make the renderer robust to missing optional metrics.

### Task 5: Rerun the prod benchmark and write findings

**Files:**
- Modify: `docs/reports/2026-03-27-single-host-capacity-report.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Verify the prod stack is healthy with profiling enabled.
2. Run the benchmark harness again.
3. Inspect route headers, SQL profiling output, and Docker stats.
4. Update the report and project status with measured bottlenecks and the next optimization order.
