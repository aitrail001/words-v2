import { expect, test } from "@playwright/test";

const PASSWORD = "password123";

test("@smoke register flow can start review and show no cards due", async ({ page }) => {
  const email = `ui-register-${Date.now()}@example.com`;

  await page.goto("/register");

  await page.getByTestId("register-email-input").fill(email);
  await page.getByTestId("register-password-input").fill(PASSWORD);
  await page.getByTestId("register-submit-button").click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Words Uncovered")).toBeVisible();

  await page.getByTestId("nav-review-link").click();
  await expect(page.getByTestId("review-start-button")).toBeVisible();

  await page.getByTestId("review-start-button").click();

  await expect(page.getByTestId("review-empty-title")).toBeVisible();
  await expect(page.getByTestId("review-empty-description")).toContainText(
    "no cards to review",
  );
});
