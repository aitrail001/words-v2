import { test, type Page } from "@playwright/test";
import {
  expectNoNextRuntimeFailure,
  expectStableRouteMarker,
} from "../helpers/route-runtime-assertions";
import type { RouteRuntimeTarget } from "../helpers/route-runtime-manifest";
import {
  injectToken,
  registerAdminViaApi,
  registerViaApi,
  waitForAppReady,
} from "../helpers/auth";
import { seedKnowledgeMapFixture } from "../helpers/knowledge-map-fixture";
import { seedAdminTimeTravelReviewFixture } from "../helpers/review-scenario-fixture";
import { seedDueReviewItem } from "../helpers/review-seed";

const LEARNER_APP_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

const LEARNER_ROUTE_RUNTIME_TARGETS = [
  {
    name: "learner-review-queue-1d",
    app: "learner",
    path: "/review/queue/1d?sort=next_review_at&order=asc",
    auth: "learner",
    marker: {
      kind: "role",
      role: "heading",
      name: /^1d$/i,
    },
  },
  {
    name: "learner-review-queue-by-due",
    app: "learner",
    path: "/review/queue/by-due",
    auth: "learner",
    marker: {
      kind: "role",
      role: "heading",
      name: /review queue by due date/i,
    },
  },
  {
    name: "learner-knowledge-list-learning",
    app: "learner",
    path: "/knowledge-list/learning",
    auth: "learner",
    marker: {
      kind: "role",
      role: "heading",
      name: "Learning Words",
    },
  },
] as const satisfies readonly RouteRuntimeTarget[];

const visitAndAssertRouteRuntime = async (
  page: Page,
  target: RouteRuntimeTarget,
) => {
  await page.goto(target.path);
  await expectStableRouteMarker(page, target);
  await expectNoNextRuntimeFailure(page);
};

test("@smoke route runtime sweep covers learner review and knowledge-list routes", async ({
  page,
  request,
}) => {
  await waitForAppReady(request, LEARNER_APP_URL);

  const user = await registerViaApi(request, "route-runtime-smoke");
  await seedDueReviewItem(user.id);
  await seedKnowledgeMapFixture(user.id);

  await injectToken(page, user.token);

  for (const target of LEARNER_ROUTE_RUNTIME_TARGETS) {
    await test.step(`visit ${target.name}`, async () => {
      await visitAndAssertRouteRuntime(page, target);
    });
  }
});

test("@smoke route runtime sweep covers admin review bucket time-travel route", async ({
  page,
  request,
}) => {
  await waitForAppReady(request, LEARNER_APP_URL);

  const admin = await registerAdminViaApi(request, "route-runtime-admin-smoke");
  const fixture = await seedAdminTimeTravelReviewFixture(admin.id);
  const target = {
    name: "learner-admin-review-queue-1d",
    app: "learner",
    path: `/admin/review-queue/1d?effective_now=${encodeURIComponent(fixture.effectiveNow)}&sort=next_review_at&order=asc`,
    auth: "admin",
    marker: {
      kind: "role",
      role: "heading",
      name: /^1d$/i,
    },
  } as const satisfies RouteRuntimeTarget;

  await injectToken(page, admin.token);
  await visitAndAssertRouteRuntime(page, target);
});
