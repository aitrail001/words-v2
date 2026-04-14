import { assignLocation } from "@/lib/browser-location";

export const redirectToLogin = (nextPath?: string): void => {
  if (typeof window === "undefined") return;

  const currentPath = nextPath ?? `${window.location.pathname}${window.location.search}`;
  const normalizedPath = currentPath || "/";

  if (normalizedPath === "/login") {
    assignLocation("/login");
    return;
  }

  assignLocation(`/login?next=${encodeURIComponent(normalizedPath)}`);
};
