# Review Dev Capacity Report

**Host budget under test:** Isolated dev stack (backend+frontend+postgres+redis on local Docker)
**Results directory:** `/Users/johnson/AI/src/words-v2/.worktrees/feat_srs_review_redesign_20260401/benchmarks/results/20260402-130216`

## Summary

- Highest tested stage meeting the initial p95/error bar: `5` VUs
- User-experience target used for the first pass: `p95 < 500ms and error rate < 5% on the isolated review workload`

## Stage Results

| VUs | RPS | p95 ms | p99 ms | Error rate | Backend max CPU % | Postgres max CPU % |
|---|---:|---:|---:|---:|---:|---:|
| 2 | 2.27 | 170.14 | n/a | 0.0000 | 7.35 | 19.88 |
| 5 | 5.80 | 190.84 | n/a | 0.0000 | 31.91 | 6.44 |
| 10 | 10.65 | 643.28 | n/a | 0.0000 | 51.69 | 9.41 |
| 15 | 14.96 | 621.67 | n/a | 0.0000 | 65.08 | 33.47 |
| 20 | 16.99 | 1309.45 | n/a | 0.0000 | 131.39 | 45.58 |
| 25 | 23.47 | 999.12 | n/a | 0.0000 | 103.89 | 35.95 |
| 30 | 24.02 | 975.90 | n/a | 0.0000 | 108.01 | 45.51 |
| 35 | 25.08 | 1354.64 | n/a | 0.0000 | 109.87 | 44.91 |
| 40 | 27.28 | 1257.43 | n/a | 0.0000 | 109.10 | 57.22 |
| 45 | 29.20 | 1861.05 | n/a | 0.0000 | 112.45 | 34.62 |
| 50 | 29.54 | 1892.80 | n/a | 0.0000 | 112.78 | 29.17 |

## Interpretation

- This report is valid only for the production-like single-host Docker stack used in this run.
- It is not a universal production concurrency claim.
- If a later stage breaches the target, the prior passing stage is the initial safe tested envelope.
