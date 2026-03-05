# Release Promotion Runbook

Use this runbook to promote a candidate from PR merge to pre-prod and production with reproducible steps.

## 1. Recommended Gate Model

Use a two-gate model:

1. Pre-merge gate on PR:
   - `Backend (lint + test)`
   - `Frontend (lint + test)`
   - `E2E Smoke (required)`
2. Post-merge gate on `main`:
   - manual `Preprod Readiness` workflow on the exact `main` commit to deploy

This keeps PR feedback fast while validating rollback and operational checks on the deployable artifact.

## 2. Why Run Readiness After Merge

Pros:

- Validates the exact `main` commit that will be deployed.
- Catches merge-commit integration effects.
- Improves auditability (`main` SHA -> release tag -> deployed artifact).

Cons:

- A bad change can land in `main` before readiness fails.
- Adds a manual promotion step.
- Requires disciplined release operations (no auto-promote on merge).

Required mitigation:

- Do not auto-deploy to pre-prod/prod from PR merge.
- Promote only after `Preprod Readiness` is green for the target `main` SHA.

## 3. Strict Promotion Sequence (8 Commands)

If PR is already merged, skip command 1.

```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
git fetch origin main && SHA="$(git rev-parse origin/main)" && TAG="release-$(date +%Y%m%d-%H%M)-${SHA:0:7}"
git tag -a "$TAG" "$SHA" -m "Release $TAG ($SHA)"
git push origin "$TAG"
gh workflow run "Preprod Readiness" --ref main
gh run watch "$(gh run list --workflow 'Preprod Readiness' --branch main --limit 1 --json databaseId -q '.[0].databaseId')"
<DEPLOY_TO_PREPROD_COMMAND_USING_TAG_OR_SHA> && curl -fsS "$PREPROD_API_URL/api/health" && curl -fsS -o /dev/null -w "%{http_code}\n" "$PREPROD_WEB_URL/register"
<PROMOTE_TO_PROD_COMMAND_USING_SAME_TAG_OR_SHA> && curl -fsS "$PROD_API_URL/api/health" && curl -fsS -o /dev/null -w "%{http_code}\n" "$PROD_WEB_URL/register"
```

## 4. Non-Negotiable Controls

- Promote the same immutable artifact (`TAG`/`SHA`) from pre-prod to prod.
- If `Preprod Readiness` fails, do not promote.
- If production verification fails, execute [`rollback.md`](./rollback.md) immediately.

