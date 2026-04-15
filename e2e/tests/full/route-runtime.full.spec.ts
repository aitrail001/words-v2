import { expect, test, type Page } from "@playwright/test";
import {
  expectNoNextRuntimeFailure,
  expectStableRouteMarker,
} from "../helpers/route-runtime-assertions";
import {
  buildAdminReviewQueueSummaryTarget,
  buildImportJobTarget,
  buildWordListTarget,
  FULL_ROUTE_RUNTIME_TARGETS,
  type RouteRuntimeTarget,
} from "../helpers/route-runtime-manifest";
import {
  injectToken,
  registerAdminViaApi,
  registerViaApi,
  waitForAppReady,
} from "../helpers/auth";
import {
  createCompletedImportJob,
  createWordListFromImportJob,
  seedRouteRuntimeCanonicalScheduleFixture,
} from "../helpers/route-runtime-fixture";
import { seedKnowledgeMapFixture } from "../helpers/knowledge-map-fixture";
import { seedAdminTimeTravelReviewFixture } from "../helpers/review-scenario-fixture";
import { seedDueReviewItem } from "../helpers/review-seed";

const LEARNER_APP_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

const visitAndAssertRouteRuntime = async (
  page: Page,
  target: RouteRuntimeTarget,
) => {
  await page.goto(target.path);
  await expectStableRouteMarker(page, target);
  await expectNoNextRuntimeFailure(page);
};

const getQueueCard = (page: Page, text: string) =>
  page.locator("li").filter({ hasText: text }).first();

const expectCanonicalQueueCard = async (page: Page, text: string) => {
  const card = getQueueCard(page, text);
  await expect(card).toBeVisible();
  await expect(card.getByText(/^Tomorrow$/i)).toBeVisible();
  await expect(card.getByText(/scheduled release:/i)).toBeVisible();
};

test("full route runtime sweep covers learner parameterized routes", async ({
  page,
  request,
}) => {
  test.slow();
  await waitForAppReady(request, LEARNER_APP_URL);

  const user = await registerViaApi(request, "route-runtime-full");
  await seedDueReviewItem(user.id);
  await seedKnowledgeMapFixture(user.id);
  const scheduleFixture = await seedRouteRuntimeCanonicalScheduleFixture(user.id);
  const importJob = await createCompletedImportJob(request, user.token);
  const wordList = await createWordListFromImportJob(
    request,
    user.token,
    importJob.id,
    `Route Runtime ${Date.now()}`,
  );

  await injectToken(page, user.token);

  const targets: RouteRuntimeTarget[] = [
    ...FULL_ROUTE_RUNTIME_TARGETS,
    buildImportJobTarget(importJob.id),
    buildWordListTarget(wordList.id),
  ];

  for (const target of targets) {
    await test.step(`visit ${target.name}`, async () => {
      await visitAndAssertRouteRuntime(page, target);
    });
  }

  await page.goto("/review/queue/by-due");
  await expect(page.getByRole("heading", { name: /review queue by due date/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Tomorrow$/i })).toBeVisible();
  await expectCanonicalQueueCard(page, scheduleFixture.phraseText);

  await page.goto(`/phrase/${scheduleFixture.phraseEntryId}`);
  await expect(page.getByText(new RegExp(`^${scheduleFixture.phraseText}$`, "i")).first()).toBeVisible();
  await expect(page.getByText(/^Next review scheduled: Tomorrow$/i)).toBeVisible();
  await expect(page.getByText(/scheduled release:/i)).toBeVisible();
  await expectNoNextRuntimeFailure(page);
});

test("full route runtime sweep covers admin review queue summary route", async ({
  page,
  request,
}) => {
  await waitForAppReady(request, LEARNER_APP_URL);

  const admin = await registerAdminViaApi(request, "route-runtime-admin-full");
  const fixture = await seedAdminTimeTravelReviewFixture(admin.id);

  await injectToken(page, admin.token);
  await visitAndAssertRouteRuntime(page, buildAdminReviewQueueSummaryTarget(fixture.effectiveNow));
});
