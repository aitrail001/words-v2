export const isProtectedPath = (pathname: string): boolean =>
  pathname === "/" ||
  pathname === "/knowledge-map" ||
  pathname.startsWith("/knowledge-list") ||
  pathname.startsWith("/knowledge/") ||
  pathname === "/settings" ||
  pathname.startsWith("/review") ||
  pathname.startsWith("/imports");

export const getAuthRedirectPath = (
  pathname: string,
  isAuthenticated: boolean,
): string | null => {
  if (!isProtectedPath(pathname) || isAuthenticated) {
    return null;
  }

  return `/login?next=${encodeURIComponent(pathname)}`;
};
