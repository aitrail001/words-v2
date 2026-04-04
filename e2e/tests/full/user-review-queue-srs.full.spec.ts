import { expect, test, type Page } from "@playwright/test";
import { injectToken, registerAdminViaApi, registerViaApi } from "../helpers/auth";
import {
  seedFailedReviewQueueFixture,
  seedGroupedReviewQueueFixture,
} from "../helpers/review-scenario-fixture";

const getBucketSection = (page: Page, heading: RegExp) =>
  page.locator("section").filter({ has: page.getByRole("heading", { name: heading }) });

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

test("learner review queue groups scheduled items, moves completed work forward, and removes known items", async ({
  page,
  request,
}) => {
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-queue-groups");
  const fixture = await seedGroupedReviewQueueFixture(user.id);

  await injectToken(page, user.token);
  await page.goto("/review/queue");

  await expect(page.getByRole("heading", { name: /review queue/i }).first()).toBeVisible();
  await expect(getBucketSection(page, /^overdue$/i)).toContainText(fixture.dueNowText);
  await expect(getBucketSection(page, /^1-3 months$/i)).toBeVisible();
  await expect(getBucketSection(page, /^6\+ months$/i)).toBeVisible();
  await expect(page.getByText(fixture.hiddenKnownText)).toHaveCount(0);
  await expect(page.getByText(fixture.hiddenToLearnText)).toHaveCount(0);
  await expect(page.getByText(fixture.tomorrowText, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.dueNowText}`, "i") }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.tomorrowText}`, "i") }),
  ).toHaveCount(0);

  await page.getByRole("link", { name: new RegExp(`Start review for ${fixture.dueNowText}`, "i") }).click();

  await expect(page).toHaveURL(/\/review\?queue_item_id=/);
  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await expect(page.getByText(new RegExp(fixture.dueNowText, "i")).first()).toBeVisible();
  await page.getByRole("button", { name: new RegExp(fixture.dueNowDefinition, "i") }).click();
  await expect(page.getByRole("button", { name: /continue review/i })).toBeVisible();
  await page.locator("#detail-review-override").selectOption({ label: "Tomorrow" });
  await page.getByRole("button", { name: /continue review/i }).click();
  await expect(page.getByTestId("review-complete-state")).toBeVisible();

  await page.goto("/review/queue");
  await expect(page.getByText(fixture.dueNowText, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.dueNowText}`, "i") }),
  ).toHaveCount(0);

  await page.getByRole("link", { name: new RegExp(`Open detail for ${fixture.tomorrowText}`, "i") }).click();
  await expect(page.getByRole("button", { name: /already knew/i })).toBeVisible();
  await page.getByRole("button", { name: /already knew/i }).click();

  await page.goto("/review/queue");
  await expect(page.getByText(fixture.tomorrowText)).toHaveCount(0);
});

test("failed review leaves the queue but no longer renders as due-now work", async ({
  page,
  request,
}) => {
  page.on("dialog", (dialog) => dialog.accept());
  const user = await registerViaApi(request, "review-queue-failed");
  const fixture = await seedFailedReviewQueueFixture(user.id);

  await injectToken(page, user.token);
  await page.goto("/review/queue");

  await expect(getBucketSection(page, /^overdue$/i)).toContainText(fixture.failedText);
  await page.getByRole("link", { name: new RegExp(`Start review for ${fixture.failedText}`, "i") }).click();

  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await page.getByRole("button", { name: /show meaning/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await finishGuidedLearningPass(page);
  await expect(page.getByTestId("review-complete-state")).toBeVisible();

  await page.goto("/review/queue");
  await expect(page.getByText(fixture.failedText)).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.failedText}`, "i") }),
  ).toHaveCount(0);
  await expect(page.getByText(fixture.futureText)).toBeVisible();
});

test("admin queue debug uses effective_now to time-travel future work into due now", async ({
  page,
  request,
}) => {
  const admin = await registerAdminViaApi(request, "review-queue-admin");
  const fixture = await seedGroupedReviewQueueFixture(admin.id);

  await injectToken(page, admin.token);
  await page.goto("/admin/review-queue");

  await expect(page.getByRole("heading", { name: /srs queue debug/i })).toBeVisible();
  await expect(page.getByText(fixture.tomorrowText, { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.tomorrowText}`, "i") }),
  ).toHaveCount(0);

  await page.goto(`/admin/review-queue?effective_now=${encodeURIComponent(fixture.effectiveNow)}`);

  await expect(page.locator('input[name="effective_now"]')).toHaveValue(fixture.effectiveNow);
  await expect(getBucketSection(page, /^due now$/i)).toContainText(fixture.tomorrowText);
  await expect(
    page.getByRole("link", { name: new RegExp(`Start review for ${fixture.tomorrowText}`, "i") }),
  ).toBeVisible();
});
