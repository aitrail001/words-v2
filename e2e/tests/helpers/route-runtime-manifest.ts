export type RouteRuntimeApp = "learner" | "admin";
export type RouteRuntimeAuthMode = "anonymous" | "learner" | "admin";
export type RouteRuntimeMarkerRole = "button" | "heading" | "link" | "textbox";

export type RouteRuntimeMarker =
  | {
      kind: "role";
      role: RouteRuntimeMarkerRole;
      name: string | RegExp;
    }
  | {
      kind: "test-id";
      testId: string;
    };

export type RouteRuntimeTarget = {
  name: string;
  app: RouteRuntimeApp;
  path: string;
  auth: RouteRuntimeAuthMode;
  marker: RouteRuntimeMarker;
};

const roleMarker = (role: RouteRuntimeMarkerRole, name: string | RegExp): RouteRuntimeMarker => ({
  kind: "role",
  role,
  name,
});

const testIdMarker = (testId: string): RouteRuntimeMarker => ({
  kind: "test-id",
  testId,
});

export const SMOKE_ROUTE_RUNTIME_TARGETS = [
  {
    name: "learner-review-queue-1d",
    app: "learner",
    path: "/review/queue/1d?sort=next_review_at&order=asc",
    auth: "learner",
    marker: roleMarker("heading", /^1d$/i),
  },
  {
    name: "learner-review-queue-by-due",
    app: "learner",
    path: "/review/queue/by-due",
    auth: "learner",
    marker: roleMarker("heading", /review queue by due date/i),
  },
  {
    name: "learner-knowledge-list-learning",
    app: "learner",
    path: "/knowledge-list/learning",
    auth: "learner",
    marker: roleMarker("heading", "Learning Words"),
  },
] as const satisfies readonly RouteRuntimeTarget[];

export const FULL_ROUTE_RUNTIME_TARGETS = [
  ...SMOKE_ROUTE_RUNTIME_TARGETS,
  {
    name: "learner-knowledge-map-range-1",
    app: "learner",
    path: "/knowledge-map/range/1",
    auth: "learner",
    marker: testIdMarker("knowledge-range-strip"),
  },
] as const satisfies readonly RouteRuntimeTarget[];

export const buildAdminReviewQueueBucketTarget = (
  effectiveNow: string,
  bucket = "1d",
): RouteRuntimeTarget => ({
  name: `learner-admin-review-queue-${bucket}`,
  app: "learner",
  path: `/admin/review-queue/${bucket}?effective_now=${encodeURIComponent(effectiveNow)}&sort=next_review_at&order=asc`,
  auth: "admin",
  marker: roleMarker("heading", new RegExp(`^${bucket}$`, "i")),
});

export const buildAdminReviewQueueSummaryTarget = (
  effectiveNow: string,
): RouteRuntimeTarget => ({
  name: "learner-admin-review-queue-summary",
  app: "learner",
  path: `/admin/review-queue?effective_now=${encodeURIComponent(effectiveNow)}`,
  auth: "admin",
  marker: roleMarker("heading", /admin review queue/i),
});

export const buildImportJobTarget = (jobId: string): RouteRuntimeTarget => ({
  name: "learner-import-job-detail",
  app: "learner",
  path: `/imports/${jobId}`,
  auth: "learner",
  marker: testIdMarker("imports-review-panel"),
});

export const buildWordListTarget = (wordListId: string): RouteRuntimeTarget => ({
  name: "learner-word-list-detail",
  app: "learner",
  path: `/word-lists/${wordListId}`,
  auth: "learner",
  marker: testIdMarker("word-list-detail-title"),
});
