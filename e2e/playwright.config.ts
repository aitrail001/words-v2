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
  projects: [
    {
      name: "chromium",
    },
  ],
});
