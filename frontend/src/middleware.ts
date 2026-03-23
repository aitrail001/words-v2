import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE_KEY } from "./lib/auth-session";
import { getAuthRedirectPath } from "./lib/auth-route-guard";

export function middleware(request: NextRequest) {
  const isAuthenticated = Boolean(
    request.cookies.get(ACCESS_TOKEN_COOKIE_KEY)?.value,
  );
  const redirectPath = getAuthRedirectPath(
    request.nextUrl.pathname,
    isAuthenticated,
  );

  if (!redirectPath) {
    return NextResponse.next();
  }

  return NextResponse.redirect(new URL(redirectPath, request.url));
}

export const config = {
  matcher: ["/", "/knowledge-map", "/knowledge-list/:path*", "/word/:path*", "/phrase/:path*", "/search", "/settings", "/review/:path*", "/imports/:path*"],
};
