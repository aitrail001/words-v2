# Pre-Prod Readiness Checklist

Use this checklist before promoting a release candidate to a pre-prod test window. This checklist covers release readiness expectations and the disposable rehearsal workflow in `.github/workflows/preprod-readiness.yml`; it is not, by itself, a substitute for verifying a real persistent pre-prod environment.

For end-to-end promotion order (merge -> tag -> deploy -> verify -> promote), see [`release-promotion.md`](./release-promotion.md).

Related distinction:

- **Preprod readiness rehearsal** = disposable Docker-based rollback/smoke drill against an ephemeral stack; today this is what `.github/workflows/preprod-readiness.yml` runs.
- **Real preprod verification** = verification against the actual deployed pre-prod environment and its persistent populated DB; use [`real-preprod-verification.md`](./real-preprod-verification.md).

## 1. Prerequisites

- Release candidate commit SHA is frozen and shared.
- GitHub Actions read/dispatch permission is confirmed.
- Local/Docker runner prerequisites for the rehearsal are available.
- Branch protection/ruleset is active on `main`.

For deployed pre-prod URLs, migration access, and persistent DB checks, use [`real-preprod-verification.md`](./real-preprod-verification.md) after `Deploy Preprod` succeeds.

## 2. Required Checks (Must Be Green)

For the exact release candidate SHA:

- `Backend (lint + test)`
- `Frontend (lint + test)`
- `E2E Smoke (required)` on PR to `main`
- `E2E Full` executed for candidate on `main` (push or manual dispatch), green

Reject candidate if any required check is failed, cancelled, or missing.

## 3. Migration + Rollback Drill Expectation

Before first pre-prod test cycle of a release window:

1. Deploy candidate to pre-prod.
2. Apply DB migrations.
3. Execute rollback drill from [`rollback.md`](./rollback.md):
   - app rollback sequence
   - post-rollback verification
4. Re-deploy candidate and re-run smoke.

Evidence required:

- migration command output
- rollback command output
- verification command output

## 4. Smoke/Full Expectations

- Smoke suite is fast gate and must pass before any merge or promote decision.
- Full suite is broader regression signal and must pass on the same candidate line before pre-prod sign-off.
- Any flaky/fail signal is treated as blocking until root cause is identified and fixed.

## 5. Go/No-Go Criteria

Go only if all are true:

- All required checks are green for candidate SHA.
- Migration completed without manual data repair.
- Rollback drill completed successfully with documented evidence.
- Post-deploy smoke checks pass in pre-prod.
- No open Sev-1/Sev-2 defects tied to the candidate.

No-Go if any item above is false.
