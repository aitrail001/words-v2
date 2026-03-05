# Rollback Runbook

Use this runbook when a release candidate causes user-visible regression or service risk in pre-prod/prod.

## 1. Trigger Conditions

Start rollback when any of the following is true:

- API health fails or sustained 5xx rate exceeds SLO.
- Login/review/import core user flows fail in smoke validation.
- Migration introduces blocking query/performance regression.
- Data integrity risk detected (incorrect writes, missing critical records).
- Incident commander declares rollback as fastest safe path.

## 2. App Rollback Sequence

1. Freeze new deploys and announce rollback start.
2. Identify last known good release (`GOOD_SHA` / image tag).
3. Roll backend, worker, frontend to `GOOD_SHA`.
4. Restart services in dependency order (DB/Redis unchanged):
   - backend
   - worker
   - frontend
5. Capture rollback start/end timestamps and deployed versions.

Example (compose-based environment):

```bash
# Update deployed refs/tags to GOOD_SHA in your deployment config, then:
docker compose up -d backend worker frontend
docker compose ps
```

## 3. DB Migration Rollback Cautions

- Prefer forward-fix over DB downgrade for most incidents.
- Do not run `alembic downgrade` in shared environments unless:
  - migration has a tested, reversible downgrade path
  - data-loss impact is explicitly reviewed
  - incident lead approves downgrade
- If schema changed and app rollback needs compatibility:
  - deploy compatibility hotfix (forward migration/fix) instead of destructive downgrade where possible

## 4. Post-Rollback Verification

Run and record:

```bash
curl -fsS "${API_BASE_URL}/api/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "${WEB_BASE_URL}/register"
```

Application checks:

- auth register/login works
- review flow loads and submits
- import endpoint accepts `.epub` upload and returns expected response code

CI signal checks:

- latest `E2E Smoke (required)` status is green for rollback target line
- if available, `E2E Full` last run for rollback target line is green

Close rollback only after verification is complete and incident notes include:

- trigger condition
- exact rollback target
- commands executed
- verification evidence

