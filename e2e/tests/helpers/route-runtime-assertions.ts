import { expect, type Locator, type Page } from "@playwright/test";
import type { RouteRuntimeMarker, RouteRuntimeTarget } from "./route-runtime-manifest";

const NEXT_RUNTIME_FAILURE_PATTERNS = [
  /application error/i,
  /^runtime error$/i,
  /an error occurred in the server components render/i,
  /switched to client rendering because the server rendering errored/i,
  /hydration failed/i,
] as const;

const NEXT_RUNTIME_FAILURE_SELECTORS = [
  "nextjs-portal",
  "[data-nextjs-dialog-overlay]",
  "[data-nextjs-toast-errors]",
] as const;

export const getRouteRuntimeMarkerLocator = (
  page: Page,
  markerOrTarget: RouteRuntimeMarker | RouteRuntimeTarget,
): Locator => {
  const marker = "marker" in markerOrTarget ? markerOrTarget.marker : markerOrTarget;

  if (marker.kind === "test-id") {
    return page.getByTestId(marker.testId);
  }

  return page.getByRole(marker.role, { name: marker.name }).first();
};

export const expectNoNextRuntimeFailure = async (page: Page): Promise<void> => {
  for (const pattern of NEXT_RUNTIME_FAILURE_PATTERNS) {
    await expect(page.getByText(pattern).first()).toHaveCount(0);
  }

  for (const selector of NEXT_RUNTIME_FAILURE_SELECTORS) {
    await expect(page.locator(selector)).toHaveCount(0);
  }
};

export const expectStableRouteMarker = async (
  page: Page,
  target: RouteRuntimeTarget,
): Promise<void> => {
  await expect(getRouteRuntimeMarkerLocator(page, target)).toBeVisible();
};
