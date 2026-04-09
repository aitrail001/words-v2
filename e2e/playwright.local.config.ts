import { defineConfig } from "@playwright/test";

const BACKEND_PORT = process.env.BACKEND_PORT ?? "8000";
const FRONTEND_PORT = process.env.FRONTEND_PORT ?? "3000";
const ADMIN_FRONTEND_PORT = process.env.ADMIN_FRONTEND_PORT ?? "3001";

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
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["junit", { outputFile: "test-results/results.xml" }],
  ],
  outputDir: "test-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  webServer: [
    {
      name: "backend",
      command:
        "bash -lc 'source .venv-backend/bin/activate && set -a && source .env.localdev && set +a && cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000} --reload'",
      url: `http://127.0.0.1:${BACKEND_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      name: "frontend",
      command:
        "bash -lc 'set -a && source .env.localdev && set +a && cd frontend && NEXT_PUBLIC_API_URL=http://localhost:${BACKEND_PORT:-8000}/api npm run dev -- --hostname 0.0.0.0 -p ${FRONTEND_PORT:-3000}'",
      url: `http://127.0.0.1:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      name: "admin-frontend",
      command:
        "bash -lc 'set -a && source .env.localdev && set +a && cd admin-frontend && NEXT_PUBLIC_API_URL=http://localhost:${BACKEND_PORT:-8000}/api npm run dev'",
      url: `http://127.0.0.1:${ADMIN_FRONTEND_PORT}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});