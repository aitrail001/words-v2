import { expect, test } from "@playwright/test";
import path from "node:path";
import { injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";
const EPUB_FIXTURE = path.resolve(process.cwd(), "tests/fixtures/epub/valid-minimal.epub");

test("@smoke admin can open EPUB cache management page", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-epub-cache-smoke");

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  await page.goto(`${adminUrl}/lexicon/epub-cache`);

  await expect(page).toHaveURL(`${adminUrl}/lexicon/epub-cache/sources`);
  await expect(page.getByTestId("lexicon-epub-cache-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "EPUB Cache Management" })).toBeVisible();
  await expect(page.getByTestId("lexicon-epub-cache-nav")).toBeVisible();
  await expect(page.getByTestId("epub-cache-sources-table")).toBeVisible();

  await page.getByRole("link", { name: "Batch Import" }).click();
  await expect(page).toHaveURL(`${adminUrl}/lexicon/epub-cache/batches`);
  await expect(page.getByTestId("lexicon-epub-cache-batches-page")).toBeVisible();
  await expect(page.getByTestId("epub-cache-recent-batches")).toBeVisible();

  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles([EPUB_FIXTURE, EPUB_FIXTURE]);
  await page.getByRole("button", { name: "Start pre-import batch" }).click();
  await expect(page.getByText(/Batch created with 2 jobs/)).toBeVisible();
  await page.getByRole("link", { name: "Open batch" }).first().click();
  await expect(page).toHaveURL(/\/lexicon\/epub-cache\/batches\/.+/);
  await expect(page.getByTestId("lexicon-epub-cache-batch-detail-page")).toBeVisible();
  await expect(page.getByTestId("epub-cache-batch-jobs")).toBeVisible();
  await expect(page.getByTestId("epub-cache-batch-job-detail")).toBeVisible();
});
