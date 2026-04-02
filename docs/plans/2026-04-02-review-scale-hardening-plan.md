# Review Scale Hardening Plan

**Status:** COMPLETED

**Scope:** Review the SRS/review redesign against `docs/prompts/2026-04-01_srs_review_ultimate_prompt.md` from a scale-readiness perspective, then benchmark the isolated dev stack and harden any concrete integrity, concurrency, or hot-path issues found.

## Goals

1. Re-audit the review slice for security, async robustness, and concurrent submit safety.
2. Produce a reproducible benchmark for the isolated review stack at `2, 5, 10, 15, 20`, then `+5` concurrency increments.
3. Use measured evidence, not intuition, to decide whether code changes are needed.
4. Keep all benchmark artifacts and status evidence in-repo so the future PR can make concrete scale claims.

## Non-goals

1. Production capacity certification.
2. Whole-repo load testing outside the review/auth hot path.
3. Replacing the full benchmark framework already used elsewhere in the repo.

## Work Items

1. Re-read the prompt and current review implementation with focus on:
   - answer verification integrity
   - duplicate-submit safety
   - row-locking and async contention
   - query amplification on `/api/reviews/queue/due`
   - auth/query overhead visible at scale
2. Add failing regression tests for any concrete integrity or concurrency flaw found.
3. Implement a review-specific benchmark runner for the isolated dev stack that:
   - seeds a large due-review pool for one authenticated benchmark user
   - reseeds before each stage to keep stage results comparable
   - exercises `/api/reviews/queue/due`, `/api/reviews/queue/stats`, and `/api/reviews/queue/{id}/submit`
   - captures latency, error rate, and container CPU
4. Run the benchmark sweep and inspect the response DB-metric headers plus any top SQL evidence.
5. Fix real problems exposed by the audit or benchmark.
6. Re-run backend tests, targeted frontend/E2E checks, and the benchmark after fixes.
7. Update `docs/status/project-status.md` with fresh evidence and a capacity baseline reference.

## Initial Risk List

1. Objective prompts may still trust client-submitted review semantics instead of the issued prompt token.
2. Due-queue generation may be fast enough for correctness tests but still scale poorly under repeated concurrent reads.
3. Benchmark numbers can be invalid if the due pool drains mid-stage or if stages reuse contaminated state.
4. Docker stats/report tooling may still assume the older production-stack container names.

## Verification Target

1. Backend regression suite for the review slice.
2. Benchmark artifacts under `benchmarks/results/<timestamp>/`.
3. Updated capacity/status docs with exact commands and measured outcomes.

## Completion Notes

1. The review slice was re-audited against the local `docs/prompts/2026-04-01_srs_review_ultimate_prompt.md` requirements with focus on answer-verification integrity, duplicate-submit safety, async contention, and due-queue query shape.
2. Concrete fixes landed for server-authoritative objective grading, prompt-token-driven outcome resolution, wider due overfetch, and request-local same-day distractor-pool reuse.
3. A reproducible isolated-stack benchmark runner now seeds dedicated benchmark review states and captures latency plus Docker CPU across `2, 5, 10, 15, 20` and `+5` VU increments through `50`.
4. Final baseline evidence lives under `benchmarks/results/20260402-101726/` and `docs/reports/2026-04-02-review-dev-capacity-report.md`.
