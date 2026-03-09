export const redirectToLogin = (nextPath?: string): void => {
  if (typeof window === "undefined") return;

  const currentPath = nextPath ?? `${window.location.pathname}${window.location.search}`;
  const normalizedPath = currentPath || "/";

  if (normalizedPath === "/login") {
    window.location.assign("/login");
    return;
  }

  window.location.assign(`/login?next=${encodeURIComponent(normalizedPath)}`);
};
