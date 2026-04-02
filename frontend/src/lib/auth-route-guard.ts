export const isProtectedPath = (pathname: string): boolean =>
  pathname === "/" ||
  pathname === "/knowledge-map" ||
  pathname.startsWith("/knowledge-list") ||
  pathname.startsWith("/word/") ||
  pathname.startsWith("/phrase/") ||
  pathname === "/search" ||
  pathname === "/settings" ||
  pathname.startsWith("/review") ||
  pathname.startsWith("/imports") ||
  pathname.startsWith("/word-lists");

export const getAuthRedirectPath = (
  pathname: string,
  isAuthenticated: boolean,
): string | null => {
  if (!isProtectedPath(pathname) || isAuthenticated) {
    return null;
  }

  return `/login?next=${encodeURIComponent(pathname)}`;
};
