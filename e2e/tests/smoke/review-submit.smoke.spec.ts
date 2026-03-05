import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { seedDueReviewItem } from "../helpers/review-seed";

test("@smoke due review item can be submitted to completion", async ({ page, request }) => {
  const user = await registerViaApi(request, "review-smoke");
  await seedDueReviewItem(request, user.token);

  await injectToken(page, user.token);
  await page.goto("/review");

  await expect(page.getByTestId("review-start-button")).toBeVisible();
  await page.getByTestId("review-start-button").click();

  await expect(page.getByTestId("review-card")).toBeVisible();
  await expect(page.getByTestId("review-card-word")).toContainText(/resilience/i);

  await page.getByTestId("review-rating-5").click();

  await expect(page.getByTestId("review-complete-title")).toBeVisible();
  await expect(page.getByTestId("review-complete-summary")).toContainText("reviewed 1 cards");
});
