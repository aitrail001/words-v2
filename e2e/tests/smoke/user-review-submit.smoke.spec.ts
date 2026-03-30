import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { seedDueReviewItem } from "../helpers/review-seed";

test("@smoke due review item can be submitted to completion", async ({ page, request }) => {
  const user = await registerViaApi(request, "review-smoke");
  await seedDueReviewItem(request, user.token);

  await injectToken(page, user.token);
  await page.goto("/review");

  await expect(page.getByRole("button", { name: /start review/i })).toBeVisible();
  await page.getByRole("button", { name: /start review/i }).click();

  await expect(page.getByPlaceholder(/type the word or phrase/i)).toBeVisible();
  await expect(page.getByText(/the capacity to recover quickly/i).first()).toBeVisible();

  await page.getByPlaceholder(/type the word or phrase/i).fill("resilience");
  await page.getByRole("button", { name: /check answer/i }).click();

  await expect(page.getByTestId("review-reveal-state")).toBeVisible();
  await expect(page.getByText(/resilience/i)).toBeVisible();
  await page.getByRole("button", { name: /continue/i }).click();

  await expect(page.getByTestId("review-complete-state")).toBeVisible();
  await expect(page.getByText(/you reviewed 1 entries/i)).toBeVisible();
});
