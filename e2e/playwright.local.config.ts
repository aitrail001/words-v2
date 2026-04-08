import { defineConfig } from "@playwright/test";

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
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  webServer: [
    {
      command:
        "bash -lc 'cd ../backend && source .venv-backend/bin/activate && set -a && source ../.env.localdev && set +a && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload'",
      url: "http://127.0.0.1:8000/api/health",
      name: "backend",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "bash -lc 'cd ../frontend && NEXT_PUBLIC_API_URL=http://localhost:8000/api npm run dev'",
      url: "http://127.0.0.1:3000",
      name: "frontend",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "bash -lc 'cd ../admin-frontend && NEXT_PUBLIC_API_URL=http://localhost:8000/api npm run dev'",
      url: "http://127.0.0.1:3001/login",
      name: "admin",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
    },
  ],
});
