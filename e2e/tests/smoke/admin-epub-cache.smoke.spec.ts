import { expect, test } from "@playwright/test";
import { injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

test("@smoke admin can open EPUB cache management page", async ({ page, request }) => {
  const user = await registerAdminViaApi(request, "admin-epub-cache-smoke");

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);

  await page.goto(`${adminUrl}/lexicon/epub-cache`);

  await expect(page).toHaveURL(`${adminUrl}/lexicon/epub-cache`);
  await expect(page.getByTestId("lexicon-epub-cache-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "EPUB Cache Management" })).toBeVisible();
  await expect(page.getByTestId("lexicon-epub-cache-nav")).toBeVisible();
  await expect(page.getByTestId("epub-cache-sources-table")).toBeVisible();
  await expect(page.getByTestId("epub-cache-recent-batches")).toBeVisible();
});
