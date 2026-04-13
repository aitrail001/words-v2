export const isProtectedPath = (pathname: string): boolean =>
  pathname === "/" || pathname.startsWith("/lexicon");

export const getAuthRedirectPath = (
  pathname: string,
  isAuthenticated: boolean,
): string | null => {
  if (!isProtectedPath(pathname) || isAuthenticated) {
    return null;
  }

  const normalizedPath = pathname === "/lexicon" ? "/lexicon/ops" : pathname;
  return `/login?next=${encodeURIComponent(normalizedPath)}`;
};
