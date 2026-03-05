# Release Promotion Runbook

Use this runbook to promote a release candidate from `main` to pre-prod and then production.

## 1. Required Repository Configuration

Configure repository variables in:
`Settings -> Secrets and variables -> Actions -> Variables (Repository)`

Required vars:

- `PREPROD_DEPLOY_COMMAND`
- `PROD_PROMOTE_COMMAND`
- `PREPROD_API_URL`
- `PREPROD_WEB_URL`
- `PROD_API_URL`
- `PROD_WEB_URL`

Command vars must execute the deploy/promote action for the exact release artifact (`SHA` or tag).

## 2. Required Gates Before Promotion

- PR gate must be green:
  - `Backend (lint + test)`
  - `Frontend (lint + test)`
  - `E2E Smoke (required)`
- Post-merge gate must be green:
  - `Preprod Readiness` on the same `release_ref` (tag or SHA) that will be deployed and promoted

## 3. Strict Promotion Sequence (UI)

1. Merge release PR to `main`.
2. Create and push release tag from `origin/main` (for example `release-YYYYMMDD-HHMM-<sha7>`).
3. Run workflow `Preprod Readiness` using **Use workflow from** = `<release_tag_or_sha>`; require green and record run URL.
4. Run workflow `Deploy Preprod` with `release_ref=<release_tag_or_sha>`.
5. Record the successful `Deploy Preprod` run id (numeric id in the run URL: `/actions/runs/<id>`).
6. Run workflow `Production Promote` with:
   - `release_ref=<same_release_tag_or_sha>`
   - `preprod_run_id=<run_id_from_step_5>`
7. Approve required environment prompts (always production; preprod only if required reviewers are configured).
8. Verify production health and close release.

## 4. Manual Workflow Inputs

`Deploy Preprod`:

- `release_ref`: tag, SHA, or branch to deploy (recommended: release tag)

`Production Promote`:

- `release_ref`: must match the artifact used in `Deploy Preprod`
- `preprod_run_id`: numeric id from the successful `Deploy Preprod` run URL (`.../actions/runs/<id>`) for the same SHA

## 5. Environment Approval Control

Enable required reviewers for the production GitHub Environment:

- `Settings -> Environments -> production -> Required reviewers`
- Keep approval mandatory before any production promotion job executes.

Optional: if you also configure required reviewers for `preprod`, expect an approval prompt during `Deploy Preprod`.

## 6. Operator Verification Commands

Before running these checks, set shell variables to your actual environment URLs:

```bash
export PREPROD_API_URL="https://<preprod-api-host>"
export PREPROD_WEB_URL="https://<preprod-web-host>"
export PROD_API_URL="https://<prod-api-host>"
export PROD_WEB_URL="https://<prod-web-host>"
```

Run after pre-prod deploy:

```bash
curl -fsS "${PREPROD_API_URL}/api/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "${PREPROD_WEB_URL}/register"
```

Run after production promotion:

```bash
curl -fsS "${PROD_API_URL}/api/health"
curl -fsS -o /dev/null -w "%{http_code}\n" "${PROD_WEB_URL}/register"
```

If production verification fails, execute [`rollback.md`](./rollback.md) immediately.
