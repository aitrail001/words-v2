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

export const SMOKE_ROUTE_RUNTIME_TARGETS = [
  {
    name: "learner-home",
    app: "learner",
    path: "/",
    auth: "learner",
    marker: roleMarker("heading", "Knowledge Map"),
  },
  {
    name: "learner-review-queue",
    app: "learner",
    path: "/review/queue",
    auth: "learner",
    marker: roleMarker("heading", /review queue/i),
  },
  {
    name: "learner-review-queue-by-due",
    app: "learner",
    path: "/review/queue/by-due",
    auth: "learner",
    marker: roleMarker("heading", /review queue by due date/i),
  },
  {
    name: "learner-knowledge-map",
    app: "learner",
    path: "/knowledge-map",
    auth: "learner",
    marker: roleMarker("heading", "Full Knowledge Map"),
  },
  {
    name: "learner-settings",
    app: "learner",
    path: "/settings",
    auth: "learner",
    marker: roleMarker("heading", "Settings"),
  },
  {
    name: "learner-admin-review-queue",
    app: "learner",
    path: "/admin/review-queue",
    auth: "admin",
    marker: roleMarker("heading", /admin review queue/i),
  },
  {
    name: "admin-home",
    app: "admin",
    path: "/",
    auth: "admin",
    marker: roleMarker("heading", "Admin Dashboard"),
  },
  {
    name: "admin-lexicon-ops",
    app: "admin",
    path: "/lexicon/ops",
    auth: "admin",
    marker: roleMarker("heading", "Lexicon Operations"),
  },
] as const satisfies readonly RouteRuntimeTarget[];

export const FULL_ROUTE_RUNTIME_TARGETS = [...SMOKE_ROUTE_RUNTIME_TARGETS] satisfies readonly RouteRuntimeTarget[];
