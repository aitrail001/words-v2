# Single-Host Production Stack and Benchmark Design

## Goal

Create a production-like single-host Docker stack for this repository, sized to fit within an effective `4 vCPU / 16 GB RAM` application budget on the target Mac host, then benchmark the main API flows with reproducible load tooling and capture the first evidence-based capacity report.

## Target Host Assumption

- Physical machine: `6 cores / 64 GB RAM`
- Shared with macOS and background workloads
- Reserved headroom: about `2 vCPU / 16 GB RAM`
- App budget for the stack under test: about `4 vCPU / 16 GB RAM`

## Why the current stack is insufficient

The existing `docker-compose.yml` is a development stack:

- backend runs `uvicorn --reload`
- frontends run `npm run dev`
- there are no explicit CPU/memory limits
- process shape does not reflect production concurrency

That stack is useful for correctness and feature testing, but not for meaningful concurrency claims.

## Production-like stack design

Add a separate `docker-compose.prod.yml` while keeping the current dev compose intact.

### Services

- `postgres`
- `redis`
- `backend`
- `worker`
- `frontend`
- `admin-frontend`
- `nginx`
- optional benchmark service or external runner using `k6`

### Runtime changes

- backend runs a production ASGI process manager with multiple workers
- frontends are built and served in production mode
- reverse proxy terminates ingress and routes traffic to backend/frontend/admin
- explicit CPU and memory limits are set for all main services
- health checks remain in place

### Initial single-host budget

Proposed starting allocation within the `4 vCPU / 16 GB` app budget:

- `postgres`: `1.5 CPU`, `4 GB`
- `redis`: `0.25 CPU`, `512 MB`
- `backend`: `1.0 CPU`, `2 GB`
- `worker`: `0.5 CPU`, `1.5 GB`
- `frontend`: `0.375 CPU`, `1 GB`
- `admin-frontend`: `0.25 CPU`, `1 GB`
- `nginx`: `0.125 CPU`, `256 MB`

This is a starting point for testing, not the final sizing answer.

## Benchmark design

### Tool

Use `k6` for repeatable API load generation.

### Flows

The first benchmark suite should cover the main user-facing and operational API paths:

- auth: login, refresh, me
- learner: overview, range, detail, search
- review: due queue, stats, submit
- admin: browse/search/detail

### Traffic model

The first sweep should be read-heavy.

Suggested rough mix:

- `55%` learner read traffic
- `20%` review traffic
- `15%` auth/session traffic
- `10%` admin traffic

### Stages

Run stepped concurrency/VU levels:

- `1`
- `5`
- `10`
- `25`
- `50`
- `100`

Stop interpreting results as acceptable once either:

- p95 breaches the latency target, or
- error rate rises materially, or
- one core/service saturates and latency rises sharply

### UX target

Use the approved target:

- p95 under `500ms` for normal API reads
- p95 under `1s` for heavier learner/detail/search flows

## Metrics capture

Capture three layers of evidence:

1. `k6` results
- request rate
- p50/p95/p99 latency
- failure rate

2. Docker/container samples
- CPU%
- memory usage
- sampled during each benchmark stage

3. App-side timing
- learner knowledge-map timing headers already emitted by the backend
- use these to separate app/query timing from total request latency where relevant

The first slice does not require full Prometheus/Grafana or `pg_stat_statements`, though those are good follow-ups.

## Deliverables

1. `docker-compose.prod.yml`
2. any supporting Dockerfile/runtime changes needed for production-mode startup
3. `k6` benchmark suite and runner scripts
4. metrics-capture helper for Docker sampling
5. capacity report documenting measured concurrency envelope on this exact host budget
6. status-board update with evidence

## Execution notes

- Keep the dev compose config in the repo
- Bring down the currently running dev stack before starting the prod-like stack
- After benchmarking, leave the production-like stack running unless instructed otherwise
- Do not claim a production concurrency number without measured evidence from this stack
