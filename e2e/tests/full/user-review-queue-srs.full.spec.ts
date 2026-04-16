import { expect, test, type Page } from "@playwright/test";
import { injectToken, registerAdminViaApi, registerViaApi } from "../helpers/auth";
import {
  seedEntryDetailNullScheduleFixture,
  seedAdminTimeTravelReviewFixture,
  seedFailedReviewQueueFixture,
  seedGroupedReviewQueueFixture,
  seedLegacyDuplicateReviewQueueFixture,
  seedLongHorizonReviewFixture,
  seedCustomReviewQueue,
  updateReviewScenarioTimezone,
} from "../helpers/review-scenario-fixture";

const getBucketSection = (page: Page, heading: RegExp) =>
  page.locator("section").filter({ has: page.getByRole("heading", { name: heading }) });

const getQueueCard = (page: Page, text: string) =>
  page.locator("li").filter({ hasText: text }).first();

const CANONICAL_DUE_LABEL = /^(Due now|Later today|Tomorrow|Overdue|In \d+ days|In a week|In 2 weeks|In a month|In \d+ months)$/i;

const expectBucketCount = async (page: Page, heading: RegExp, count: number) => {
  await expect(getBucketSection(page, heading)).toContainText(
    new RegExp(`${count} scheduled review item${count === 1 ? "" : "s"}`, "i"),
  );
};

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const openBucket = async (page: Page, bucketLabel: string) => {
  await page.getByRole("link", { name: new RegExp(`Open ${bucketLabel} bucket`, "i") }).click();
};

const startReviewFromQueue = async (page: Page, text: string) => {
  const startLink = page.getByRole("link", { name: new RegExp(`Start review for ${text}`, "i") });
  await expect(startLink).toHaveAttribute("href", /\/review\?queue_item_id=/);
  await Promise.all([page.waitForURL(/\/review\?queue_item_id=/), startLink.click()]);
};

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
  await expect(getBucketSection(page, /^30d$/i)).toBeVisible();
  await expect(getBucketSection(page, /^180d$/i)).toBeVisible();
  await expect(page.getByText(fixture.hiddenKnownText)).toHaveCount(0);
  await expect(page.getByText(fixture.hiddenToLearnText)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /^start review$/i })).toBeVisible();

  await openBucket(page, "1d");
  await expect(page.getByText(fixture.dueNowText, { exact: true })).toBeVisible();
  await startReviewFromQueue(page, fixture.dueNowText);
  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await expect(page.getByText(new RegExp(fixture.dueNowText, "i")).first()).toBeVisible();
  await page.getByRole("button", { name: new RegExp(fixture.dueNowDefinition, "i") }).click();
  await expect(page.getByRole("button", { name: /continue review/i })).toBeVisible();
  await page.getByRole("button", { name: /override/i }).click();
  await expect(page.getByLabel(/override next review/i)).toBeVisible();
  await page.locator("#detail-review-override").selectOption("1d");
  await page.getByRole("button", { name: /confirm next review change/i }).click();
  await page.getByRole("button", { name: /continue review/i }).click();
  await expect(page.getByTestId("review-complete-state")).toBeVisible();

  await page.goto("/review/queue");
  await openBucket(page, "1d");
  await expect(page.getByText(fixture.dueNowText, { exact: true })).toBeVisible();
  await page.goto("/review/queue");
  await openBucket(page, "7d");
  await expect(page.getByText(fixture.tomorrowText, { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`Start review for ${fixture.tomorrowText}`, "i") })).toHaveCount(0);

  await page.goto("/review/queue");
  await openBucket(page, "7d");
  await page.getByRole("link", { name: new RegExp(`Open detail for ${fixture.tomorrowText}`, "i") }).click();
  await expect(page.getByRole("button", { name: /already knew/i })).toBeVisible();
  await page.getByRole("button", { name: /already knew/i }).click();

  await page.goto("/review/queue");
  await expect(page.getByRole("link", { name: /open 7d bucket/i })).toHaveCount(0);
  await expect(page.getByText(fixture.tomorrowText)).toHaveCount(0);
});

test("learner can switch between stage-grouped and due-date-grouped queue views", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-queue-by-due");
  const fixture = await seedGroupedReviewQueueFixture(user.id);

  await injectToken(page, user.token);
  await page.goto("/review/queue");

  await expect(page.getByRole("link", { name: /group by due date/i })).toBeVisible();
  await page.getByRole("link", { name: /group by due date/i }).click();

  await expect(page).toHaveURL(/\/review\/queue\/by-due$/);
  await expect(page.getByRole("heading", { name: /review queue by due date/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^1d$/i })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /^7d$/i })).toHaveCount(0);
  const dueNowCard = getQueueCard(page, fixture.dueNowText);
  const tomorrowCard = getQueueCard(page, fixture.tomorrowText);
  await expect(dueNowCard).toBeVisible();
  await expect(tomorrowCard).toBeVisible();
  await expect(dueNowCard.getByText(CANONICAL_DUE_LABEL).first()).toBeVisible();
  await expect(tomorrowCard.getByText(CANONICAL_DUE_LABEL).first()).toBeVisible();
  await expect(page.getByText(/SRS stage 1d/i)).toBeVisible();
  await expect(page.getByText(/SRS stage 7d/i)).toBeVisible();

  await page.getByRole("link", { name: /group by stage/i }).click();
  await expect(page).toHaveURL(/\/review\/queue$/);
  await expect(getBucketSection(page, /^1d$/i)).toBeVisible();
  await expect(getBucketSection(page, /^7d$/i)).toBeVisible();
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

  await openBucket(page, "1d");
  await expect(page.getByText(fixture.failedText, { exact: true })).toBeVisible();
  await startReviewFromQueue(page, fixture.failedText);

  await expect(page.getByTestId("review-active-state")).toBeVisible();
  await page.getByRole("button", { name: /show meaning/i }).click();
  await expect(page.getByTestId("review-relearn-state")).toBeVisible();
  await finishGuidedLearningPass(page);
  await expect(page.getByTestId("review-complete-state")).toBeVisible();

  await page.goto("/review/queue");
  await expect(getBucketSection(page, /^1d$/i)).toBeVisible();
  await expect(getBucketSection(page, /^7d$/i)).toBeVisible();
});

test("admin queue debug uses effective_now to time-travel future work into active review buckets", async ({
  page,
  request,
}) => {
  const admin = await registerAdminViaApi(request, "review-queue-admin");
  const fixture = await seedAdminTimeTravelReviewFixture(admin.id);

  await injectToken(page, admin.token);
  await page.goto("/admin/review-queue");

  await expect(page.getByRole("heading", { name: /admin review queue/i })).toBeVisible();
  await expect(getBucketSection(page, /^7d$/i)).toBeVisible();

  await page.goto(`/admin/review-queue?effective_now=${encodeURIComponent(fixture.effectiveNow)}`);

  await expect(page.locator('input[name="effective_now"]')).toHaveValue(fixture.effectiveNow);
  await expect(getBucketSection(page, /^7d$/i)).toBeVisible();
  await expect(getBucketSection(page, /^30d$/i)).toBeVisible();
});

test("long-horizon SRS items render in the learner queue without waiting months", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-queue-long-horizon");
  const fixture = await seedLongHorizonReviewFixture(user.id);

  await injectToken(page, user.token);
  await page.goto("/review/queue");
  await expect(getBucketSection(page, /^180d$/i)).toBeVisible();
  await openBucket(page, "180d");
  await expect(page.getByText(new RegExp(`^${escapeRegExp(fixture.reviewText)}$`, "i"))).toBeVisible();
});

test("detail page keeps the canonical label even when the exact release time is unavailable", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-detail-null-schedule");
  const fixture = await seedEntryDetailNullScheduleFixture(user.id);

  await injectToken(page, user.token);
  await page.goto(`/${fixture.entryType}/${fixture.entryId}`);

  await expect(page.getByText(new RegExp(`^${escapeRegExp(fixture.displayText)}$`, "i")).first()).toBeVisible();
  await expect(page.getByText(/^next review scheduled:/i)).toBeVisible();
  await expect(
    page.getByText(
      /^next review scheduled: (Due now|Later today|Tomorrow|Overdue|In \d+ days|In a week|In 2 weeks|In a month|In \d+ months)$/i,
    ),
  ).toBeVisible();
  await expect(page.getByText(/approximately:/i)).toHaveCount(0);
  await expect(page.getByText(/scheduled release:/i)).toBeVisible();
  await expect(page.getByText(/scheduled time not set yet/i)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^override$/i })).toBeVisible();
});

test("legacy duplicate queue rows do not inflate learner-visible counts", async ({
  page,
  request,
}) => {
  const user = await registerViaApi(request, "review-queue-legacy-duplicates");
  const fixture = await seedLegacyDuplicateReviewQueueFixture(user.id);

  await injectToken(page, user.token);
  await page.goto("/review/queue");

  await expect(
    page.locator("section").first().getByText("2 scheduled review items"),
  ).toBeVisible();
  await openBucket(page, fixture.bucket);
  await expect(page.getByText("2 items in this bucket")).toBeVisible();
  await expect(page.getByText(fixture.visibleTexts[0], { exact: true })).toBeVisible();
  await expect(page.getByText(fixture.visibleTexts[1], { exact: true })).toBeVisible();
});

test("same-day reviews align to one release instant", async ({ request }) => {
  const admin = await registerAdminViaApi(request, "review-queue-alignment");
  const releaseInstant = "2026-04-12T18:00:00Z";
  const beforeRelease = "2026-04-12T17:59:59Z";
  const dueAt = new Date(releaseInstant);
  await seedCustomReviewQueue(admin.id, {
    timezone: "Australia/Melbourne",
    items: [
      {
        scenarioKey: "entry-to-definition",
        status: "learning",
        nextDueAt: dueAt,
        dueReviewDate: "2026-04-13",
        minDueAtUtc: dueAt,
        lastReviewedAt: new Date("2026-04-10T00:00:00Z"),
      },
      {
        scenarioKey: "definition-to-entry",
        status: "learning",
        nextDueAt: dueAt,
        dueReviewDate: "2026-04-13",
        minDueAtUtc: dueAt,
        lastReviewedAt: new Date("2026-04-10T05:00:00Z"),
      },
      {
        scenarioKey: "situation",
        status: "learning",
        nextDueAt: dueAt,
        dueReviewDate: "2026-04-13",
        minDueAtUtc: dueAt,
        lastReviewedAt: new Date("2026-04-10T12:30:00Z"),
      },
    ],
  });

  const apiBaseUrl = process.env.E2E_API_URL ?? "http://127.0.0.1:8000/api";
  const authHeaders = { Authorization: `Bearer ${admin.token}` };

  const beforeSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(beforeRelease)}`,
    { headers: authHeaders },
  );
  expect(beforeSummaryResponse.ok()).toBeTruthy();
  const beforeSummary = await beforeSummaryResponse.json();
  expect(beforeSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 3,
        has_due_now: false,
      }),
    ]),
  );

  const beforeBucketResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/buckets/1d?effective_now=${encodeURIComponent(beforeRelease)}`,
    { headers: authHeaders },
  );
  expect(beforeBucketResponse.ok()).toBeTruthy();
  const beforeBucket = await beforeBucketResponse.json();
  expect(beforeBucket.items).toHaveLength(3);
  expect(
    new Set(
      beforeBucket.items.map((item: { min_due_at_utc: string | null }) => item.min_due_at_utc),
    ),
  ).toEqual(
    new Set([releaseInstant]),
  );
  expect(
    new Set(
      beforeBucket.items.map((item: { due_review_date: string | null }) => item.due_review_date),
    ),
  ).toEqual(new Set(["2026-04-13"]));

  const releaseSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(releaseInstant)}`,
    { headers: authHeaders },
  );
  expect(releaseSummaryResponse.ok()).toBeTruthy();
  const releaseSummary = await releaseSummaryResponse.json();
  expect(releaseSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 3,
        has_due_now: true,
      }),
    ]),
  );
});

test("eastward travel does not unlock early", async ({ request }) => {
  const admin = await registerAdminViaApi(request, "review-queue-eastward");
  const effectiveNow = "2026-04-13T10:30:00Z";
  const dueAt = new Date("2026-04-13T11:00:00Z");
  await seedCustomReviewQueue(admin.id, {
    timezone: "America/Los_Angeles",
    items: [
      {
        scenarioKey: "entry-to-definition",
        status: "learning",
        nextDueAt: dueAt,
        dueReviewDate: "2026-04-13",
        minDueAtUtc: dueAt,
        lastReviewedAt: new Date("2026-04-12T18:00:00Z"),
      },
    ],
  });

  const apiBaseUrl = process.env.E2E_API_URL ?? "http://127.0.0.1:8000/api";
  const authHeaders = { Authorization: `Bearer ${admin.token}` };

  const beforeSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(effectiveNow)}`,
    { headers: authHeaders },
  );
  expect(beforeSummaryResponse.ok()).toBeTruthy();
  const beforeSummary = await beforeSummaryResponse.json();
  expect(beforeSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 1,
        has_due_now: false,
      }),
    ]),
  );

  await updateReviewScenarioTimezone(admin.id, "Pacific/Kiritimati");

  const afterSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(effectiveNow)}`,
    { headers: authHeaders },
  );
  expect(afterSummaryResponse.ok()).toBeTruthy();
  const afterSummary = await afterSummaryResponse.json();
  expect(afterSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 1,
        has_due_now: false,
      }),
    ]),
  );
});

test("already-due remains due after timezone change", async ({ request }) => {
  const admin = await registerAdminViaApi(request, "review-queue-sticky-due");
  const effectiveNow = "2026-04-12T18:00:00Z";
  const dueAt = new Date(effectiveNow);
  await seedCustomReviewQueue(admin.id, {
    timezone: "Australia/Melbourne",
    items: [
      {
        scenarioKey: "definition-to-entry",
        status: "learning",
        nextDueAt: dueAt,
        dueReviewDate: "2026-04-13",
        minDueAtUtc: dueAt,
        lastReviewedAt: new Date("2026-04-10T04:00:00Z"),
      },
    ],
  });

  const apiBaseUrl = process.env.E2E_API_URL ?? "http://127.0.0.1:8000/api";
  const authHeaders = { Authorization: `Bearer ${admin.token}` };

  const beforeSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(effectiveNow)}`,
    { headers: authHeaders },
  );
  expect(beforeSummaryResponse.ok()).toBeTruthy();
  const beforeSummary = await beforeSummaryResponse.json();
  expect(beforeSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 1,
        has_due_now: true,
      }),
    ]),
  );

  await updateReviewScenarioTimezone(admin.id, "America/Los_Angeles");

  const afterSummaryResponse = await request.get(
    `${apiBaseUrl}/reviews/admin/queue/summary?effective_now=${encodeURIComponent(effectiveNow)}`,
    { headers: authHeaders },
  );
  expect(afterSummaryResponse.ok()).toBeTruthy();
  const afterSummary = await afterSummaryResponse.json();
  expect(afterSummary.groups).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        bucket: "1d",
        count: 1,
        has_due_now: true,
      }),
    ]),
  );
});
