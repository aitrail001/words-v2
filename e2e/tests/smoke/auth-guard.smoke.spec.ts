import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("@smoke auth guard redirects unauthenticated users to login with next", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?next=%2F$/);
  await expect(page.getByTestId("login-form")).toBeVisible();

  await page.goto("/review");
  await expect(page).toHaveURL(/\/login\?next=%2Freview$/);
  await expect(page.getByTestId("login-form")).toBeVisible();
});

test("@smoke auth guard allows authenticated users on protected routes", async ({ page, request }) => {
  const user = await registerViaApi(request, "auth-guard");

  await injectToken(page, user.token);

  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.goto("/review");
  await expect(page).toHaveURL(/\/review$/);
  await expect(page.getByTestId("review-start-button")).toBeVisible();
});
