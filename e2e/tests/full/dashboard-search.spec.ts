import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { ensureResilienceVocabularyFixture } from "../helpers/vocabulary-fixture";

test("dashboard search returns seeded word", async ({ page, request }) => {
  await ensureResilienceVocabularyFixture();
  const user = await registerViaApi(request, "dashboard-search");
  await injectToken(page, user.token);

  await page.goto("/");

  await page.getByTestId("home-search-input").fill("resilience");
  await expect(
    page.getByTestId("home-search-result-item").filter({ hasText: /resilience/i }).first(),
  ).toBeVisible();
});
