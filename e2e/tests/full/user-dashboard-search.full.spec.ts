import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { ensureResilienceVocabularyFixture } from "../helpers/vocabulary-fixture";

test("search returns seeded word", async ({ page, request }) => {
  await ensureResilienceVocabularyFixture();
  const user = await registerViaApi(request, "dashboard-search");
  await injectToken(page, user.token);

  await page.goto("/search");

  await page.getByPlaceholder("Search words and phrases").fill("resilience");
  await expect(
    page.getByRole("link", { name: /resilience/i }).first(),
  ).toBeVisible();
});
