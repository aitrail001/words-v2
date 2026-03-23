import { expect, test } from "@playwright/test";
import { apiUrl, authHeaders, injectAdminToken, registerAdminViaApi, waitForAppReady } from "../helpers/auth";

const adminUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001";

test("@smoke admin auth guard redirects unauthenticated users to login", async ({ page }) => {
  await waitForAppReady(page.request, adminUrl);
  await page.goto(`${adminUrl}/lexicon`);

  await expect(page).toHaveURL(/\/login\?next=%2Flexicon%2Fops$/);
  await expect(page.getByTestId("login-form")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Admin Log In" })).toBeVisible();
});

test("@smoke admin session reaches lexicon review shell with a real admin account", async ({
  page,
  request,
}) => {
  const user = await registerAdminViaApi(request, "admin-auth-smoke");

  const meResponse = await request.get(`${apiUrl}/auth/me`, {
    headers: authHeaders(user.token),
  });
  expect(meResponse.ok()).toBeTruthy();
  const me = (await meResponse.json()) as { role: string };
  expect(me.role).toBe("admin");

  await waitForAppReady(request, adminUrl);
  await injectAdminToken(page, user.token, adminUrl);
  await page.goto(`${adminUrl}/`);

  await expect(page).toHaveURL(`${adminUrl}/`);
  await expect(page.getByTestId("admin-home-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Admin Dashboard" })).toBeVisible();

  await page.getByTestId("admin-home-lexicon-link").click();
  await expect(page).toHaveURL(`${adminUrl}/lexicon/ops`);
  await expect(page.getByTestId("lexicon-ops-page")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Lexicon Operations" })).toBeVisible();
});
