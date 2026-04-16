import { expect, test, type Page } from "@playwright/test";
import {
  expectNoNextRuntimeFailure,
  expectStableRouteMarker,
} from "../helpers/route-runtime-assertions";
import {
  buildAdminReviewQueueBucketTarget,
  SMOKE_ROUTE_RUNTIME_TARGETS,
  type RouteRuntimeTarget,
} from "../helpers/route-runtime-manifest";
import {
  injectToken,
  registerAdminViaApi,
  registerViaApi,
  waitForAppReady,
} from "../helpers/auth";
import { seedKnowledgeMapFixture } from "../helpers/knowledge-map-fixture";
import { seedAdminTimeTravelReviewFixture } from "../helpers/review-scenario-fixture";
import { seedDueReviewItem } from "../helpers/review-seed";
import { seedRouteRuntimeCanonicalScheduleFixture } from "../helpers/route-runtime-fixture";

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

const CANONICAL_DUE_LABEL = /^(Due now|Later today|Tomorrow|Overdue|In \d+ days|In a week|In 2 weeks|In a month|In \d+ months)$/i;

const expectCanonicalQueueCard = async (page: Page, text: string) => {
  const card = getQueueCard(page, text);
  await expect(card).toBeVisible();
  const dueLabel = card.getByText(CANONICAL_DUE_LABEL).first();
  await expect(dueLabel).toBeVisible();
  await expect(card.getByText(/scheduled release:/i)).toBeVisible();
  return (await dueLabel.textContent())?.trim() ?? null;
};

test("@smoke route runtime sweep covers learner review and knowledge-list routes", async ({
  page,
  request,
}) => {
  await waitForAppReady(request, LEARNER_APP_URL);

  const user = await registerViaApi(request, "route-runtime-smoke");
  await seedDueReviewItem(user.id);
  await seedKnowledgeMapFixture(user.id);
  const scheduleFixture = await seedRouteRuntimeCanonicalScheduleFixture(user.id);

  await injectToken(page, user.token);

  for (const target of SMOKE_ROUTE_RUNTIME_TARGETS) {
    await test.step(`visit ${target.name}`, async () => {
      await visitAndAssertRouteRuntime(page, target);
    });
  }

  await page.goto("/review/queue/1d?sort=next_review_at&order=asc");
  const dueLabel = await expectCanonicalQueueCard(page, scheduleFixture.wordText);
  expect(dueLabel).toBeTruthy();

  await page.goto(`/word/${scheduleFixture.wordEntryId}`);
  await expect(page.getByText(new RegExp(`^${scheduleFixture.wordText}$`, "i")).first()).toBeVisible();
  await expect(page.getByText(`Next review scheduled: ${dueLabel}`, { exact: true })).toBeVisible();
  await expect(page.getByText(/scheduled release:/i)).toBeVisible();
  await expectNoNextRuntimeFailure(page);
});

test("@smoke route runtime sweep covers admin review bucket time-travel route", async ({
  page,
  request,
}) => {
  await waitForAppReady(request, LEARNER_APP_URL);

  const admin = await registerAdminViaApi(request, "route-runtime-admin-smoke");
  const fixture = await seedAdminTimeTravelReviewFixture(admin.id);
  const target = buildAdminReviewQueueBucketTarget(fixture.effectiveNow, "7d");

  await injectToken(page, admin.token);
  await visitAndAssertRouteRuntime(page, target);
  await expectCanonicalQueueCard(page, fixture.futureText);
  await expect(page.getByText(/admin diagnostics/i)).toBeVisible();
});
