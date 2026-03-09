# Pre-Prod Readiness Checklist

Use this checklist before promoting a release candidate to pre-prod test window.

For end-to-end promotion order (merge -> tag -> deploy -> verify -> promote), see [`release-promotion.md`](./release-promotion.md).

## 1. Prerequisites

- Release candidate commit SHA is frozen and shared.
- Pre-prod environment is reachable (API, learner frontend, admin frontend, DB, Redis).
- Operator access confirmed:
  - GitHub Actions read/dispatch permission.
  - Deployment credentials for pre-prod.
  - DB migration tooling access (`alembic`).
- Branch protection/ruleset is active on `main`.

Quick health probe:

```bash
curl -fsS "${API_BASE_URL}/api/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "${WEB_BASE_URL}/register"
curl -fsS -o /dev/null -w "%{http_code}\n" "${ADMIN_WEB_BASE_URL}/login"
```

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
