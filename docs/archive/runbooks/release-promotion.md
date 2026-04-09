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
- Post-merge rehearsal gate must be green:
  - `Preprod Readiness Rehearsal` on the same `release_ref` (tag or SHA) that will be deployed and promoted
- Real pre-prod verification against the deployed environment and persistent DB must be completed per [`real-preprod-verification.md`](./real-preprod-verification.md).

## 3. Strict Promotion Sequence (UI)

1. Merge release PR to `main`.
2. Create and push release tag from `origin/main` (for example `release-YYYYMMDD-HHMM-<sha7>`).
3. Run workflow `Preprod Readiness Rehearsal` using **Use workflow from** = `<release_tag_or_sha>`; require green and record run URL.
4. Run workflow `Deploy Preprod` with `release_ref=<release_tag_or_sha>`.
5. Run the real environment verification in [`real-preprod-verification.md`](./real-preprod-verification.md) against the deployed pre-prod environment; record migration, smoke, and rollback evidence as applicable.
6. Record the successful `Deploy Preprod` run id (numeric id in the run URL: `/actions/runs/<id>`).
7. Run workflow `Production Promote` with:
   - `release_ref=<same_release_tag_or_sha>`
   - `preprod_run_id=<run_id_from_step_5>`
8. Approve required environment prompts (always production; preprod only if required reviewers are configured).
9. Verify production health and close release.

## 4. Detailed `gh` Command Sequence

Use this when GitHub CLI is installed and authenticated (`gh auth status`).

```bash
# 0) Set repo context
OWNER="aitrail001"
REPO="words-v2"

# 1) Tag the exact release commit from origin/main
git fetch origin main
SHA="$(git rev-parse origin/main)"
TAG="release-$(date -u +%Y%m%d-%H%M)-${SHA:0:7}"
git tag -a "${TAG}" "${SHA}" -m "Release ${TAG} (${SHA})"
git push origin "${TAG}"

# 2) Helper to get most recent workflow_dispatch run id for a workflow + SHA
latest_run_id() {
  local workflow_name="$1"
  local release_sha="$2"
  gh run list \
    --repo "${OWNER}/${REPO}" \
    --workflow "${workflow_name}" \
    --json databaseId,headSha,event,createdAt \
    --limit 50 \
    --jq ".[] | select(.event==\"workflow_dispatch\" and .headSha==\"${release_sha}\") | .databaseId" \
    | head -n 1
}

# 3) Run Preprod Readiness Rehearsal on the same release tag, then wait
gh workflow run "Preprod Readiness Rehearsal" --repo "${OWNER}/${REPO}" --ref "${TAG}"
PREPROD_READINESS_RUN_ID="$(latest_run_id "Preprod Readiness Rehearsal" "${SHA}")"
gh run watch "${PREPROD_READINESS_RUN_ID}" --repo "${OWNER}/${REPO}" --exit-status

# 4) Run Deploy Preprod on the same release tag, then wait
gh workflow run "Deploy Preprod" --repo "${OWNER}/${REPO}" --ref "${TAG}" -f release_ref="${TAG}"
DEPLOY_PREPROD_RUN_ID="$(latest_run_id "Deploy Preprod" "${SHA}")"
gh run watch "${DEPLOY_PREPROD_RUN_ID}" --repo "${OWNER}/${REPO}" --exit-status

# 5) Execute the real pre-prod verification runbook against the deployed environment
#    (manual/operator step documented in docs/runbooks/real-preprod-verification.md)

# 6) Run Production Promote with same release_ref + deploy-preprod run id
gh workflow run "Production Promote" \
  --repo "${OWNER}/${REPO}" \
  --ref "${TAG}" \
  -f release_ref="${TAG}" \
  -f preprod_run_id="${DEPLOY_PREPROD_RUN_ID}"
PROMOTE_PROD_RUN_ID="$(latest_run_id "Production Promote" "${SHA}")"
gh run watch "${PROMOTE_PROD_RUN_ID}" --repo "${OWNER}/${REPO}" --exit-status

# 7) Operator verification
echo "Release tag: ${TAG}"
echo "Release SHA: ${SHA}"
echo "Deploy-preprod run id: ${DEPLOY_PREPROD_RUN_ID}"
```

## 5. Detailed `git` + UI Sequence (No `gh`)

Use this when you do not want to install GitHub CLI.

```bash
# 1) Tag the exact release commit from origin/main
git fetch origin main
SHA="$(git rev-parse origin/main)"
TAG="release-$(date -u +%Y%m%d-%H%M)-${SHA:0:7}"
git tag -a "${TAG}" "${SHA}" -m "Release ${TAG} (${SHA})"
git push origin "${TAG}"

# 2) Keep these values for workflow inputs and audit notes
echo "Release tag: ${TAG}"
echo "Release SHA: ${SHA}"
```

Then dispatch workflows in GitHub UI (same repository):

1. `Actions` -> `Preprod Readiness Rehearsal` -> `Run workflow`
   Set `Use workflow from` to `${TAG}`.
2. `Actions` -> `Deploy Preprod` -> `Run workflow`
   Set `Use workflow from` to `${TAG}` and `release_ref=${TAG}`.
3. Execute [`real-preprod-verification.md`](./real-preprod-verification.md) against the deployed pre-prod environment and record evidence.
4. Open the successful `Deploy Preprod` run and copy numeric run id from URL:
   `.../actions/runs/<id>`.
5. `Actions` -> `Production Promote` -> `Run workflow`
   Set `Use workflow from` to `${TAG}`, `release_ref=${TAG}`, and `preprod_run_id=<id>`.

## 6. Manual Workflow Inputs

`Deploy Preprod`:

- `release_ref`: tag, SHA, or branch to deploy (recommended: release tag)

`Production Promote`:

- `release_ref`: must match the artifact used in `Deploy Preprod`
- `preprod_run_id`: numeric id from the successful `Deploy Preprod` run URL (`.../actions/runs/<id>`) for the same SHA

## 7. Environment Approval Control

Enable required reviewers for the production GitHub Environment:

- `Settings -> Environments -> production -> Required reviewers`
- Keep approval mandatory before any production promotion job executes.

Optional: if you also configure required reviewers for `preprod`, expect an approval prompt during `Deploy Preprod`.

## 8. Operator Verification Commands

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
