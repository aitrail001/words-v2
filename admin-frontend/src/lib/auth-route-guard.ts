export const isProtectedPath = (pathname: string): boolean =>
  pathname === "/" || pathname.startsWith("/lexicon");

export const getAuthRedirectPath = (
  pathname: string,
  isAuthenticated: boolean,
): string | null => {
  if (!isProtectedPath(pathname) || isAuthenticated) {
    return null;
  }

  return `/login?next=${encodeURIComponent(pathname)}`;
};
