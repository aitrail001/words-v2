import { expect, test } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import {
  LEARN_WORD,
  KNOWLEDGE_PHRASE,
  KNOWLEDGE_WORD,
  seedKnowledgeMapFixture,
} from "../helpers/knowledge-map-fixture";

test("@smoke learner knowledge map supports mixed catalog browsing and persisted statuses", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "knowledge-map");
  const fixture = await seedKnowledgeMapFixture(user.id);

  await injectToken(page, user.token);

  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText("Words Uncovered")).toBeVisible();
  await expect(page.getByRole("link", { name: /knew/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /started/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /to learn/i })).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /started/i }).click();
  await expect(page).toHaveURL(/\/knowledge-list\/learning$/);
  await expect(page.getByRole("heading", { name: "Learning Words" })).toBeVisible();
  await expect(page.getByText(KNOWLEDGE_PHRASE, { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Alphabetic" })).toBeVisible();
  await page.getByRole("button", { name: "Alphabetic" }).click();
  await expect(page.getByRole("button", { name: "Hardest First" })).toBeVisible();
  await page.getByRole("button", { name: "Hardest First" }).click();
  await expect(page.getByRole("button", { name: "Easiest First" })).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /to learn/i }).click();
  await expect(page).toHaveURL(/\/knowledge-list\/to-learn$/);
  await expect(page.getByRole("heading", { name: "To Learn" })).toBeVisible();
  await expect(page.getByText(LEARN_WORD, { exact: false })).toBeVisible();

  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Search" })).toBeVisible();
  await page.getByPlaceholder("Search words and phrases").fill("bank");
  const phraseResult = page.getByRole("link", { name: new RegExp(KNOWLEDGE_PHRASE, "i") });
  await expect(phraseResult).toBeVisible();
  await phraseResult.click();

  await expect(page).toHaveURL(new RegExp(`/phrase/${fixture.phraseId}$`));
  await expect(page.getByRole("heading", { name: KNOWLEDGE_PHRASE })).toBeVisible();
  await expect(page.getByText("To depend on someone or something.").first()).toBeVisible();
  await expect(page.getByText("depender de")).toBeVisible();
  await expect(page.getByText("You can bank on me when the deadline gets tight.").first()).toBeVisible();
  await expect(page.getByText("Status: Learning")).toBeVisible();

  await page.getByRole("button", { name: "Known" }).click();
  await expect(page.getByText("Status: Known")).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /discover/i }).click();
  await expect(page).toHaveURL(/\/knowledge-map/);
  await expect(page.getByRole("heading", { name: "Full Knowledge Map" })).toBeVisible();
  await expect(page.getByText(/range 1-100/i)).toBeVisible();

  await page.goto("/");
  await page.getByRole("link", { name: /learn next:/i }).click();
  await expect(page).toHaveURL(new RegExp(`/word/${fixture.learnWordId}$`));
  await expect(page.getByRole("heading", { name: LEARN_WORD })).toBeVisible();
  await expect(page.getByText("tambor")).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("Learning")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Translation" })).toBeVisible();
  await page.getByRole("button", { name: /show translations by default/i }).click();
  await expect(page.getByRole("button", { name: /show translations by default/i })).toContainText("Off");

  await page.goto("/search");
  await page.getByPlaceholder("Search words and phrases").fill("drum");
  await expect(page.getByText("tambor")).toHaveCount(0);
});
