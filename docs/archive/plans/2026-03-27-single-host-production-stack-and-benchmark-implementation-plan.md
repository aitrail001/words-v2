# Single-Host Production Stack and Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a single-host production-like Docker stack, benchmark the main API flows with `k6`, capture Docker resource metrics during the run, and produce the first evidence-based capacity report for this exact host budget.

**Architecture:** Keep development compose intact while adding a separate production-like compose file with explicit resource limits and production runtime commands. Use a repeatable `k6` suite plus Docker stats sampling to benchmark the core API flows and write a capacity report from measured results.

**Tech Stack:** Docker Compose, FastAPI/Uvicorn/Gunicorn, Next.js production runtime, Nginx, k6, shell scripts, Markdown

---

### Task 1: Add production-stack docs and runtime shape

**Files:**
- Create: `docker-compose.prod.yml`
- Create or modify: `deploy/nginx/nginx.conf`
- Modify as needed: backend/frontend/admin Docker runtime files
- Modify: `docs/status/project-status.md`

**Step 1: Define production service topology**

Include:
- postgres
- redis
- backend
- worker
- frontend
- admin-frontend
- nginx

**Step 2: Set production runtime commands**

- backend: multi-worker production serving, no reload
- frontend/admin: build + start, no dev server

**Step 3: Add explicit CPU and memory limits**

Target the approved effective app budget.

### Task 2: Add benchmark harness

**Files:**
- Create: `benchmarks/k6/main.js`
- Create: `benchmarks/k6/lib/*.js` if needed
- Create: `scripts/benchmark/run-single-host-benchmark.sh`
- Create: `scripts/benchmark/capture-docker-stats.sh`

**Step 1: Implement API benchmark scenarios**

Cover:
- auth
- learner overview/range/detail/search
- review queue/stats/submit
- admin browse/search/detail

**Step 2: Add staged concurrency profile**

Use stepped VU stages for the first sweep.

**Step 3: Write outputs to files**

Persist raw benchmark summaries and sampled docker stats under a benchmark results directory.

### Task 3: Stop the current dev stack and bring up the prod-like stack

**Files:**
- Use compose files only; no repo content changes required unless startup issues demand patches

**Step 1: Bring down the running dev stack**

**Step 2: Build and start the production-like stack**

**Step 3: Verify health endpoints and ingress**

### Task 4: Run initial concurrency sweep

**Files:**
- Output under a results directory such as `benchmarks/results/<timestamp>/`

**Step 1: Run benchmark stages**

Record:
- latency percentiles
- throughput
- failures
- docker resource samples

**Step 2: Note saturation point**

Find the highest stage that still meets the approved p95 budget.

### Task 5: Write the first capacity report

**Files:**
- Create: `docs/reports/2026-03-27-single-host-capacity-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Summarize environment**

State:
- exact stack shape
- resource limits
- benchmark scenarios
- host budget assumption

**Step 2: Report evidence**

Include:
- tested stages
- p50/p95/p99
- failures
- docker CPU/memory samples
- first bottleneck observed

**Step 3: State initial safe tested envelope**

Phrase it as “tested on this stack,” not a universal production claim.

### Task 6: Final verification

**Files:**
- Verify compose and benchmark assets

**Step 1: Verify compose config parses**

**Step 2: Verify production stack starts successfully**

**Step 3: Verify benchmark scripts run and produce result artifacts**

**Step 4: Update status board with the verification evidence**
