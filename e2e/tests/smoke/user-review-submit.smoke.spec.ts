import { expect, test, type Page } from "@playwright/test";
import { injectToken, registerViaApi } from "../helpers/auth";
import { seedKnowledgeMapFixture } from "../helpers/knowledge-map-fixture";
import {
  fetchReviewScenarioStateSnapshot,
  seedCustomReviewQueue,
} from "../helpers/review-scenario-fixture";
import { seedDueReviewItem } from "../helpers/review-seed";

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const finishGuidedLearningPass = async (page: Page) => {
  for (let step = 0; step < 10; step += 1) {
    const nextMeaning = page.getByRole("button", { name: /next meaning/i });
    if (await nextMeaning.count()) {
      await nextMeaning.click();
      continue;
    }
    const finishLearning = page.getByRole("button", { name: /finish learning/i });
    if (await finishLearning.count()) {
      await finishLearning.click();
    }
    return;
  }
  throw new Error("Guided relearn did not finish within 10 steps.");
};

test("@smoke due review item can be submitted to completion", async ({ page, request }) => {
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-smoke");
  const dueFixture = await seedDueReviewItem(user.id);

  await injectToken(page, user.token);
  await page.goto("/review");

  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await expect(page.getByText(new RegExp(escapeRegExp(dueFixture.displayText), "i")).first()).toBeVisible();

  if (await page.getByPlaceholder(/type the word or phrase/i).count()) {
    await page.getByPlaceholder(/type the word or phrase/i).fill(dueFixture.displayText);
    await page.getByRole("button", { name: /check answer/i }).click();
  } else {
    await page.getByRole("button", { name: new RegExp(escapeRegExp(dueFixture.definition), "i") }).click();
  }

  await expect(page.getByRole("button", { name: /continue review/i })).toBeVisible();
  await page.getByRole("button", { name: /continue review/i }).click();
  await expect(page.getByTestId("review-complete-state")).toBeVisible();
});

test("@smoke learn-now word detail flow enters the learning pass before review prompts", async ({ page, request }) => {
  test.setTimeout(90_000);
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-learn-now");
  const fixture = await seedKnowledgeMapFixture(user.id);

  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = async () => undefined;
  });

  await injectToken(page, user.token);
  await page.goto(`/word/${fixture.learnWordId}`);

  await expect(page.getByRole("heading", { name: /drum/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /learn now/i })).toBeVisible();

  const statusUpdateResponse = page.waitForResponse((response) =>
    response.url().includes(`/api/knowledge-map/entries/word/${fixture.learnWordId}/status`)
      && response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: /learn now/i }).click();
  expect((await statusUpdateResponse).ok()).toBeTruthy();

  await expect(page).toHaveURL(new RegExp(`/review\\?entry_type=word&entry_id=${fixture.learnWordId}$`));
  await expect(page.getByTestId("review-learning-state")).toBeVisible();
  await expect(page.getByRole("heading", { name: /drum/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /finish learning/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /show meaning/i })).toHaveCount(0);
  await expect(page.getByText(/queue item .* not found/i)).toHaveCount(0);

  await page.getByRole("button", { name: /finish learning/i }).click();

  await expect(page.getByTestId("review-complete-state")).toBeVisible();
  await expect(page.getByText(/you reviewed 1 entries/i)).toBeVisible();
  await expect(page.getByText(/queue item .* not found/i)).toHaveCount(0);

  await page.goto(`/word/${fixture.learnWordId}`);
  await expect(page.getByText(/approximately: tomorrow/i)).toBeVisible();
  await expect(page.getByText(/next review scheduled:/i)).toBeVisible();

  await page.goto("/review");
  await expect(page.getByTestId("review-empty-state")).toBeVisible();
  await expect(page.getByTestId("review-empty-title")).toHaveText(/no entries due/i);
});

test("@smoke same-session retry stays separate from the official schedule", async ({ page, request }) => {
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-retry-separation");
  await seedCustomReviewQueue(user.id, {
    timezone: "Australia/Melbourne",
    items: [
      {
        scenarioKey: "sentence-gap",
        status: "learning",
        dueAt: new Date(Date.now() - 60_000),
        lastReviewedAt: new Date(Date.now() - 24 * 60 * 60 * 1000),
      },
    ],
  });
  const seededState = await fetchReviewScenarioStateSnapshot(user.id, "sentence-gap");

  await injectToken(page, user.token);
  await page.goto(`/review?queue_item_id=${encodeURIComponent(seededState.queueItemId)}`);

  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await page.getByRole("button", { name: /show meaning/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();

  const stateAfterFailure = await fetchReviewScenarioStateSnapshot(user.id, "sentence-gap");
  expect(stateAfterFailure.lastOutcome).toBe("wrong");
  expect(stateAfterFailure.dueReviewDate).toBeTruthy();
  expect(stateAfterFailure.minDueAtUtc).toBeTruthy();
  expect(stateAfterFailure.nextDueAt).toBeTruthy();
  expect(stateAfterFailure.recheckDueAt).toBeTruthy();
  expect(stateAfterFailure.lastReviewedAt).toBeTruthy();

  const officialDueAt = new Date(stateAfterFailure.minDueAtUtc!);
  const nextDueAt = new Date(stateAfterFailure.nextDueAt!);
  const recheckDueAt = new Date(stateAfterFailure.recheckDueAt!);
  const reviewedAt = new Date(stateAfterFailure.lastReviewedAt!);

  expect(nextDueAt.getTime()).toBe(officialDueAt.getTime());
  expect(recheckDueAt.getTime()).toBeGreaterThan(reviewedAt.getTime() + 9 * 60 * 1000);
  expect(recheckDueAt.getTime()).toBeLessThan(reviewedAt.getTime() + 11 * 60 * 1000);
  expect(officialDueAt.getTime()).toBeGreaterThan(recheckDueAt.getTime() + 30 * 60 * 1000);
});
