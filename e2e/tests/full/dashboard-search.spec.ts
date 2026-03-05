import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";

test("dashboard search returns seeded word", async ({ page, request }) => {
  const user = await registerViaApi(request, "dashboard-search");
  await injectToken(page, user.token);

  await page.goto("/");

  await page.getByTestId("home-search-input").fill("resil");
  await expect(page.getByTestId("home-search-result-item").first()).toContainText(
    "resilience",
  );
});
