# E2E Admin/User Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic required `E2E Full` GitHub gate with separate required `E2E Admin` and `E2E User` jobs that both depend on `E2E Smoke`, while renaming specs to make admin/user ownership explicit.

**Architecture:** Keep the current Docker-based smoke-first CI structure, but split the full Playwright execution into two dedicated jobs driven by explicit npm scripts and path-based spec ownership. Rename user-facing smoke/full specs to `user-*`, promote selected admin flows into a new full admin lane, and preserve a tiny mixed smoke subset for fast failure.

**Tech Stack:** GitHub Actions, Playwright, TypeScript, npm, Docker Compose

---

### Task 1: Rename learner/user specs and add failing script expectations

**Files:**
- Modify: `e2e/package.json`
- Rename: `e2e/tests/smoke/auth-contract.smoke.spec.ts`
- Rename: `e2e/tests/smoke/auth-guard.smoke.spec.ts`
- Rename: `e2e/tests/smoke/import-create.smoke.spec.ts`
- Rename: `e2e/tests/smoke/import-domain.smoke.spec.ts`
- Rename: `e2e/tests/smoke/knowledge-map.smoke.spec.ts`
- Rename: `e2e/tests/smoke/register-review-empty.smoke.spec.ts`
- Rename: `e2e/tests/smoke/review-prompt-families.smoke.spec.ts`
- Rename: `e2e/tests/smoke/review-submit.smoke.spec.ts`
- Rename: `e2e/tests/full/dashboard-search.spec.ts`
- Rename: `e2e/tests/full/import-terminal.full.spec.ts`

- [ ] **Step 1: Add failing npm script definitions in `e2e/package.json`**

Add script placeholders for:

```json
{
  "scripts": {
    "test:admin": "playwright test tests/full/admin-*.full.spec.ts",
    "test:user": "playwright test tests/full/user-*.full.spec.ts"
  }
}
```

Expected initial failure reason: no matching renamed files or missing admin full files yet.

- [ ] **Step 2: Rename learner-owned smoke specs to `user-*`**

Apply these exact renames:

```text
e2e/tests/smoke/auth-contract.smoke.spec.ts -> e2e/tests/smoke/user-auth-contract.smoke.spec.ts
e2e/tests/smoke/auth-guard.smoke.spec.ts -> e2e/tests/smoke/user-auth-guard.smoke.spec.ts
e2e/tests/smoke/import-create.smoke.spec.ts -> e2e/tests/smoke/user-import-create.smoke.spec.ts
e2e/tests/smoke/import-domain.smoke.spec.ts -> e2e/tests/smoke/user-import-domain.smoke.spec.ts
e2e/tests/smoke/knowledge-map.smoke.spec.ts -> e2e/tests/smoke/user-knowledge-map.smoke.spec.ts
e2e/tests/smoke/register-review-empty.smoke.spec.ts -> e2e/tests/smoke/user-register-review-empty.smoke.spec.ts
e2e/tests/smoke/review-prompt-families.smoke.spec.ts -> e2e/tests/smoke/user-review-prompt-families.smoke.spec.ts
e2e/tests/smoke/review-submit.smoke.spec.ts -> e2e/tests/smoke/user-review-submit.smoke.spec.ts
```

- [ ] **Step 3: Rename learner-owned full specs to `user-*`**

Apply these exact renames:

```text
e2e/tests/full/dashboard-search.spec.ts -> e2e/tests/full/user-dashboard-search.full.spec.ts
e2e/tests/full/import-terminal.full.spec.ts -> e2e/tests/full/user-import-terminal.full.spec.ts
```

- [ ] **Step 4: Run a file-inventory check**

Run:

```bash
find e2e/tests/smoke -maxdepth 1 -type f | sort
find e2e/tests/full -maxdepth 1 -type f | sort
```

Expected:
- learner smoke files use `user-*`
- admin smoke files still use `admin-*`
- learner full files use `user-*`

- [ ] **Step 5: Run the renamed user full command to verify current behavior**

Run:

```bash
npm --prefix e2e run test:user -- --list
```

Expected:
- only `tests/full/user-dashboard-search.full.spec.ts`
- only `tests/full/user-import-terminal.full.spec.ts`

### Task 2: Create the admin full lane from existing durable admin scenarios

**Files:**
- Create: `e2e/tests/full/admin-compiled-review.full.spec.ts`
- Create: `e2e/tests/full/admin-jsonl-review.full.spec.ts`
- Create: `e2e/tests/full/admin-lexicon-ops-import.full.spec.ts`
- Create: `e2e/tests/full/admin-lexicon-voice-import.full.spec.ts`
- Create: `e2e/tests/full/admin-compiled-review-bulk-job.full.spec.ts`
- Modify: any shared helper imports used by those specs if paths/names need adjustment

- [ ] **Step 1: Copy the current admin smoke flows into full-lane files**

Source these existing files:

```text
e2e/tests/smoke/admin-compiled-review-flow.smoke.spec.ts
e2e/tests/smoke/admin-jsonl-review-flow.smoke.spec.ts
e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts
e2e/tests/smoke/admin-lexicon-voice-import-flow.smoke.spec.ts
e2e/tests/smoke/admin-compiled-review-bulk-job.smoke.spec.ts
```

Create corresponding full files under `e2e/tests/full/` with `.full.spec.ts` suffix and `admin-` prefix preserved.

- [ ] **Step 2: Remove smoke tagging from the new admin full files**

Edit the copied tests so the test names no longer contain `@smoke`.

Example transformation:

```ts
test("@smoke admin can review and export a compiled lexicon batch", async ({ page, request }) => {
```

to:

```ts
test("admin can review and export a compiled lexicon batch", async ({ page, request }) => {
```

- [ ] **Step 3: Keep the original smoke files intact**

Do not delete the original admin smoke files. They remain the fast subset for `E2E Smoke`.

- [ ] **Step 4: Run the admin full command to verify selection**

Run:

```bash
npm --prefix e2e run test:admin -- --list
```

Expected:
- only `tests/full/admin-*.full.spec.ts`
- no `tests/smoke/*`
- no `tests/full/user-*`

### Task 3: Split the CI workflow into smoke, admin, and user lanes

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Replace `e2e-full` with `e2e-admin` and `e2e-user`**

In `.github/workflows/ci.yml`, remove the single:

```yaml
e2e-full:
  name: E2E Full (required)
```

and replace it with:

```yaml
e2e-admin:
  name: E2E Admin (required)
  needs: [e2e-smoke]

e2e-user:
  name: E2E User (required)
  needs: [e2e-smoke]
```

- [ ] **Step 2: Keep the bootstrap structure the same**

For both new jobs, preserve the existing steps:

```yaml
- checkout
- setup-node
- npm ci --prefix e2e
- docker compose up ...
- wait for backend/frontends
- alembic upgrade head
- docker compose run ... playwright ...
- upload artifacts
- docker compose down ...
```

Only the Playwright command and artifact names should differ.

- [ ] **Step 3: Point each job at its dedicated npm script**

Use:

```yaml
playwright sh -lc "cd /workspace/e2e && npm run test:admin"
```

for admin, and:

```yaml
playwright sh -lc "cd /workspace/e2e && npm run test:user"
```

for user.

- [ ] **Step 4: Rename artifacts for clarity**

Use distinct artifact names:

```yaml
name: playwright-admin-artifacts
name: playwright-user-artifacts
```

- [ ] **Step 5: Run a workflow sanity check**

Run:

```bash
python - <<'PY'
from pathlib import Path
import yaml
doc = yaml.safe_load(Path(".github/workflows/ci.yml").read_text())
assert "e2e-smoke" in doc["jobs"]
assert "e2e-admin" in doc["jobs"]
assert "e2e-user" in doc["jobs"]
assert "e2e-full" not in doc["jobs"]
assert doc["jobs"]["e2e-admin"]["needs"] == ["e2e-smoke"]
assert doc["jobs"]["e2e-user"]["needs"] == ["e2e-smoke"]
PY
```

Expected: PASS

### Task 4: Update status documentation and verify the split locally

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a status-log entry**

Record that:
- the required gate is now `E2E Smoke`, `E2E Admin`, and `E2E User`
- the learner specs were renamed to `user-*`
- admin full coverage now exists as its own lane

- [ ] **Step 2: Verify the smoke file set still exists**

Run:

```bash
find e2e/tests/smoke -maxdepth 1 -type f | sort
```

Expected:
- both `admin-*` and `user-*` smoke files are present

- [ ] **Step 3: Verify the full file sets**

Run:

```bash
find e2e/tests/full -maxdepth 1 -type f | sort
```

Expected:
- both `admin-*.full.spec.ts` and `user-*.full.spec.ts` files exist

- [ ] **Step 4: Verify npm script routing**

Run:

```bash
npm --prefix e2e run test:admin -- --list
npm --prefix e2e run test:user -- --list
```

Expected:
- admin command only lists admin full files
- user command only lists user full files

- [ ] **Step 5: Verify the smoke suite still resolves**

Run:

```bash
npm --prefix e2e run test:smoke:ci -- --list
```

Expected:
- smoke still picks up the intended tiny mixed subset

- [ ] **Step 6: Run final lightweight verification**

Run:

```bash
npm --prefix e2e run typecheck
```

Expected: PASS

- [ ] **Step 7: Record final evidence in status**

Update `docs/status/project-status.md` with the exact verification commands and outcomes from this implementation.
