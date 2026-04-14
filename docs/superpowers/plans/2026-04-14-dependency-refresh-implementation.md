# Dependency Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the requested frontend, admin frontend, E2E, and lexicon Node dependencies, regenerate lockfiles, fix upgrade-induced compatibility issues, and verify the repo remains review-ready.

**Architecture:** Keep the existing repo structure and package-manager layout intact, perform a coordinated dependency refresh, then remediate only the smallest failing boundaries exposed by the new versions. Verify locally at workspace scope first, then run the repo gates and rebuild the graph after code changes.

**Tech Stack:** Next.js 16, React 19, Jest, ts-jest, ESLint flat config, Tailwind 4, TypeScript 6, Playwright, Zustand, OpenAI Node SDK, Make-based CI gates, graphify.

---

### Task 1: Create Isolated Worktree And Capture Baseline

**Files:**
- Modify: `.gitignore`
- Create: `.worktrees/dependency-refresh-2026-04-14/`
- Reference: `AGENTS.md`
- Reference: `docs/superpowers/specs/2026-04-14-dependency-refresh-design.md`

- [ ] **Step 1: Verify the worktree directory is ignored**

```gitignore
.worktrees/
```

Run: `git check-ignore -q .worktrees || printf '\n.worktrees/\n' >> .gitignore`
Expected: `.worktrees` is ignored by Git after the command.

- [ ] **Step 2: Commit the ignore fix if `.gitignore` changed**

```bash
git add .gitignore
git commit -m "chore: ignore local worktrees"
```

Expected: either a new commit is created or `git status --short .gitignore` is empty because the ignore rule already existed.

- [ ] **Step 3: Refresh `main` and create the worktree**

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git worktree add .worktrees/dependency-refresh-2026-04-14 -b feat/dependency-refresh-2026-04-14 main
```

Expected: the new branch is created from updated `main`, and the worktree exists at `.worktrees/dependency-refresh-2026-04-14`.

- [ ] **Step 4: Bootstrap the worktree**

```bash
make worktree-bootstrap
```

Expected: shared Python environments are linked and workspace-local `node_modules` are installed without errors.

- [ ] **Step 5: Capture baseline verification before changing dependencies**

```bash
make test-frontend
make test-admin
cd e2e && npm run typecheck
```

Expected: baseline results are recorded. If any command already fails on the fresh worktree, stop and note the failure before proceeding so upgrade regressions are not conflated with pre-existing issues.

- [ ] **Step 6: Commit the baseline-only setup branch state if Task 1 created a `.gitignore` change**

```bash
git status --short
```

Expected: only intentional Task 1 changes are present before moving to dependency edits.

### Task 2: Upgrade Requested Manifest Versions And Regenerate Lockfiles

**Files:**
- Modify: `frontend/package.json`
- Modify: `admin-frontend/package.json`
- Modify: `e2e/package.json`
- Modify: `tools/lexicon/node/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/pnpm-lock.yaml`
- Modify: `admin-frontend/package-lock.json`
- Modify: `e2e/package-lock.json`
- Modify: `e2e/pnpm-lock.yaml`
- Modify: `tools/lexicon/node/package-lock.json`

- [ ] **Step 1: Write the manifest edits for `frontend/package.json`**

```json
{
  "dependencies": {
    "next": "^16.2.3",
    "react": "^19.2.5",
    "react-dom": "^19.2.5",
    "zustand": "^5.0.12"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.2.2",
    "@types/node": "^25.6.0",
    "@types/react": "^19.2.0",
    "@types/react-dom": "^19.2.0",
    "eslint": "^10.2.0",
    "jest": "^30.3.0",
    "jest-environment-jsdom": "^30.3.0",
    "tailwindcss": "^4.2.2",
    "ts-jest": "^29.4.9",
    "typescript": "^6.0.2"
  }
}
```

Expected: `frontend/package.json` contains the requested versions while preserving unrelated entries.

- [ ] **Step 2: Write the manifest edits for `admin-frontend/package.json`**

```json
{
  "dependencies": {
    "next": "^16.2.3",
    "react": "^19.2.5",
    "react-dom": "^19.2.5",
    "zustand": "^5.0.12"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4.2.2",
    "@types/node": "^25.6.0",
    "@types/react": "^19.2.0",
    "@types/react-dom": "^19.2.0",
    "eslint": "^10.2.0",
    "jest": "^30.3.0",
    "jest-environment-jsdom": "^30.3.0",
    "tailwindcss": "^4.2.2",
    "ts-jest": "^29.4.9",
    "typescript": "^6.0.2"
  }
}
```

Expected: `admin-frontend/package.json` matches the requested targets while preserving unrelated entries.

- [ ] **Step 3: Write the manifest edits for `e2e/package.json` and `tools/lexicon/node/package.json`**

```json
{
  "devDependencies": {
    "@types/node": "^25.6.0",
    "@types/pg": "^8.20.0",
    "typescript": "^6.0.2"
  }
}
```

```json
{
  "dependencies": {
    "openai": "^6.34.0"
  }
}
```

Expected: `e2e/package.json` and `tools/lexicon/node/package.json` reflect the requested versions.

- [ ] **Step 4: Regenerate the frontend lockfiles**

```bash
cd frontend && npm install
cd frontend && pnpm install --lockfile-only
```

Expected: `frontend/package-lock.json` and `frontend/pnpm-lock.yaml` are refreshed without unresolved dependency errors.

- [ ] **Step 5: Regenerate the admin frontend, E2E, and lexicon Node lockfiles**

```bash
cd admin-frontend && npm install
cd e2e && npm install
cd e2e && pnpm install --lockfile-only
cd tools/lexicon/node && npm install
```

Expected: each lockfile is refreshed in place and install logs show resolved dependency trees for the requested versions.

- [ ] **Step 6: Run a red-state verification pass after lockfile refresh**

```bash
cd frontend && npm test -- --runInBand
cd admin-frontend && npm test -- --runInBand
cd e2e && npm run typecheck
node tools/lexicon/node/openai_compatible_responses.mjs < /dev/null
```

Expected: at least one command may fail because of upgrade-induced incompatibility. Capture the first real failures; these are the RED signals for the remediation tasks below.

- [ ] **Step 7: Commit the dependency refresh and RED evidence**

```bash
git add frontend/package.json frontend/package-lock.json frontend/pnpm-lock.yaml admin-frontend/package.json admin-frontend/package-lock.json e2e/package.json e2e/package-lock.json e2e/pnpm-lock.yaml tools/lexicon/node/package.json tools/lexicon/node/package-lock.json
git commit -m "test: refresh dependency manifests and lockfiles"
```

Expected: the commit is on the feature branch and represents the RED checkpoint for any failing verification created by the upgrade.

### Task 3: Fix Frontend Compatibility Regressions With TDD

**Files:**
- Modify: `frontend/jest.config.js`
- Modify: `frontend/jest.setup.ts`
- Modify: `frontend/eslint.config.mjs`
- Modify: `frontend/postcss.config.mjs`
- Modify: `frontend/tsconfig.json`
- Modify: `frontend/src/lib/store.ts`
- Modify: `frontend/src/lib/__tests__/knowledge-map-client.test.ts`
- Modify: `frontend/src/lib/__tests__/api-client.test.ts`
- Modify: `frontend/src/app/**/__tests__/*.test.tsx`

- [ ] **Step 1: Isolate the first failing frontend target and keep it RED**

```bash
cd frontend && npm test -- --runInBand src/lib/__tests__/knowledge-map-client.test.ts
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: identify the first concrete frontend failure caused by the upgrade and keep one command red until the fix is ready. Do not edit production code until one failing target is confirmed.

- [ ] **Step 2: If Jest 30 or ts-jest is the failing boundary, update `frontend/jest.config.js` minimally**

```js
const config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  transform: {
    "^.+\\.tsx?$": ["ts-jest", {
      tsconfig: {
        jsx: "react-jsx",
      },
      isolatedModules: true,
    }],
  },
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
};

module.exports = config;
```

Expected: only add the minimum option changes needed for Jest 30 compatibility. If the current config already works, leave this file unchanged.

- [ ] **Step 3: If ESLint 10 or Next 16 linting is the failing boundary, keep the flat config narrow**

```js
import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**"],
  },
  ...nextVitals,
];

export default eslintConfig;
```

Expected: preserve the existing flat-config shape and only adjust imports or export syntax if the upgraded toolchain requires it.

- [ ] **Step 4: If TypeScript 6 or Zustand 5 exposes typing failures, fix the smallest affected module first**

```ts
import { create } from "zustand";

interface AppState {
  isInitialized: boolean;
  setInitialized: (value: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  isInitialized: false,
  setInitialized: (value) => set({ isInitialized: value }),
}));
```

Expected: keep `frontend/src/lib/store.ts` functionally identical unless the new types require a minimal generic or inference adjustment.

- [ ] **Step 5: Re-run the exact failing frontend target until it turns GREEN**

```bash
cd frontend && npm test -- --runInBand src/lib/__tests__/knowledge-map-client.test.ts
cd frontend && npm run lint
cd frontend && npm run build
```

Expected: the previously failing frontend command now passes. If a new failure appears, fix it in a separate red-green loop before broadening the scope.

- [ ] **Step 6: Run the canonical frontend repo target**

```bash
make test-frontend
```

Expected: the frontend Jest suite invoked by the repo target passes.

- [ ] **Step 7: Commit the minimal frontend fix**

```bash
git add frontend/jest.config.js frontend/jest.setup.ts frontend/eslint.config.mjs frontend/postcss.config.mjs frontend/tsconfig.json frontend/src
git commit -m "fix: restore frontend compatibility after dependency refresh"
```

Expected: the commit contains only upgrade-induced frontend compatibility fixes.

### Task 4: Fix Admin Frontend Compatibility Regressions With TDD

**Files:**
- Modify: `admin-frontend/jest.config.js`
- Modify: `admin-frontend/jest.setup.ts`
- Modify: `admin-frontend/eslint.config.mjs`
- Modify: `admin-frontend/postcss.config.mjs`
- Modify: `admin-frontend/tsconfig.json`
- Modify: `admin-frontend/src/lib/__tests__/words-client.test.ts`
- Modify: `admin-frontend/src/lib/__tests__/lexicon-jobs-client.test.ts`
- Modify: `admin-frontend/src/app/**/__tests__/*.test.tsx`

- [ ] **Step 1: Isolate the first failing admin frontend target and keep it RED**

```bash
cd admin-frontend && npm test -- --runInBand src/lib/__tests__/words-client.test.ts
cd admin-frontend && npm run lint
cd admin-frontend && npm run build
```

Expected: identify the first admin-specific failure induced by the refresh and keep one target red before editing code or config.

- [ ] **Step 2: Apply the smallest Jest or TypeScript compatibility fix in the existing config files**

```js
const config = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  transform: {
    "^.+\\.tsx?$": ["ts-jest", {
      tsconfig: {
        jsx: "react-jsx",
      },
      isolatedModules: true,
    }],
  },
  modulePathIgnorePatterns: ["<rootDir>/.next/"],
  testPathIgnorePatterns: ["<rootDir>/node_modules/", "<rootDir>/.next/"],
  watchPathIgnorePatterns: ["<rootDir>/.next/"],
};

module.exports = config;
```

Expected: preserve the current Jest shape and only adjust the parts required by the upgraded toolchain.

- [ ] **Step 3: If linting fails, keep the admin flat ESLint config minimal**

```js
import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  {
    ignores: [".next/**", "node_modules/**", "coverage/**"],
  },
  ...nextVitals,
];

export default eslintConfig;
```

Expected: any ESLint 10 compatibility changes remain local to the config entrypoint.

- [ ] **Step 4: Re-run the exact failing admin target until it turns GREEN**

```bash
cd admin-frontend && npm test -- --runInBand src/lib/__tests__/words-client.test.ts
cd admin-frontend && npm run lint
cd admin-frontend && npm run build
```

Expected: the originally failing admin frontend command now passes.

- [ ] **Step 5: Run the canonical admin repo target**

```bash
make test-admin
```

Expected: the admin Jest suite invoked by the repo target passes.

- [ ] **Step 6: Commit the minimal admin frontend fix**

```bash
git add admin-frontend/jest.config.js admin-frontend/jest.setup.ts admin-frontend/eslint.config.mjs admin-frontend/postcss.config.mjs admin-frontend/tsconfig.json admin-frontend/src
git commit -m "fix: restore admin frontend compatibility after dependency refresh"
```

Expected: only admin upgrade-remediation files are included.

### Task 5: Fix E2E And Lexicon Node Compatibility Regressions

**Files:**
- Modify: `e2e/tsconfig.json`
- Modify: `e2e/playwright.config.ts`
- Modify: `e2e/playwright.local.config.ts`
- Modify: `e2e/tests/**/*.ts`
- Modify: `tools/lexicon/node/openai_compatible_responses.mjs`

- [ ] **Step 1: Confirm the E2E typecheck failure in RED**

```bash
cd e2e && npm run typecheck
```

Expected: if TypeScript 6 or Node 25 types expose errors, keep the command red until the first concrete issue is identified. If it already passes, do not edit E2E files.

- [ ] **Step 2: Apply the smallest E2E config or helper fix**

```ts
import { defineConfig } from "@playwright/test";

const htmlReportDir = process.env.PLAYWRIGHT_HTML_OUTPUT_DIR ?? "playwright-report";
const junitReportFile = process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE ?? "test-results/results.xml";
const resultsDir = process.env.PLAYWRIGHT_RESULTS_DIR ?? "test-results";
const screenshotMode = process.env.PLAYWRIGHT_SCREENSHOT_MODE ?? "only-on-failure";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: htmlReportDir }],
    ["junit", { outputFile: junitReportFile }],
  ],
  outputDir: resultsDir,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: screenshotMode as "off" | "on" | "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  projects: [{ name: "chromium" }],
});
```

Expected: keep changes local to the failing type boundary. Do not change suite behavior unless the new compiler or types require it.

- [ ] **Step 3: Re-run E2E typecheck until GREEN**

```bash
cd e2e && npm run typecheck
```

Expected: the E2E TypeScript target passes.

- [ ] **Step 4: Validate the lexicon Node transport against the upgraded OpenAI SDK**

```bash
cd tools/lexicon/node && npm install
printf '%s\n' '{"request_id":"dry-run","base_url":"https://example.invalid","api_key":"test","model":"gpt-test","prompt":"hello"}' | node openai_compatible_responses.mjs
```

Expected: the script starts, parses input, and returns a structured JSON error envelope rather than crashing on import or client construction.

- [ ] **Step 5: If the OpenAI SDK broke the transport contract, patch only the client boundary**

```js
const client = new OpenAI({
  apiKey,
  baseURL,
  defaultHeaders: { "x-api-key": apiKey },
});
```

Expected: keep the existing stdin/stdout protocol intact and only change the `OpenAI` request construction if the upgraded SDK requires it.

- [ ] **Step 6: Commit the E2E and lexicon compatibility fixes**

```bash
git add e2e/tsconfig.json e2e/playwright.config.ts e2e/playwright.local.config.ts e2e/tests tools/lexicon/node/openai_compatible_responses.mjs
git commit -m "fix: restore e2e and lexicon compatibility after dependency refresh"
```

Expected: only E2E and lexicon remediation files are included.

### Task 6: Final Verification, Gate Execution, And Graph Rebuild

**Files:**
- Modify: `graphify-out/**`
- Review: `.codex/**`
- Review: `.env.stack.ci`
- Review: `.env.stack.gate`
- Review: `.githooks/pre-push`

- [ ] **Step 1: Run targeted local verification for all changed workspaces**

```bash
make test-frontend
make test-admin
cd e2e && npm run typecheck
cd tools/lexicon/node && npm install
```

Expected: all targeted local checks used during remediation are green.

- [ ] **Step 2: Run the repo gate commands outside the sandbox on first attempt**

```bash
make gate-fast
make gate-full
```

Expected: both gates pass. If `gate-full` fails after `gate-fast` passes, fix the specific failing suite and re-run the gate that failed.

- [ ] **Step 3: Rebuild the graph after code changes**

```bash
uv run --with graphifyy python3.13 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"
```

Expected: `graphify-out/` is refreshed without errors.

- [ ] **Step 4: Inspect the final diff and verification state**

```bash
git status --short
git diff --stat
```

Expected: only intentional dependency-refresh files, lockfiles, and graph output changes remain.

- [ ] **Step 5: Commit the final verification artifacts and graph refresh**

```bash
git add graphify-out
git commit -m "chore: refresh graph after dependency upgrade verification"
```

Expected: the graph refresh commit exists only if `graphify-out/` changed.

- [ ] **Step 6: Prepare the branch for review**

```bash
git log --oneline --decorate -5
```

Expected: the branch history clearly shows RED, GREEN, and any final refactor/verification commits for this task.

