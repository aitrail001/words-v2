import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { ACCESS_TOKEN_COOKIE_KEY } from "./src/lib/auth-session";
import { getAuthRedirectPath } from "./src/lib/auth-route-guard";

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
  matcher: ["/", "/lexicon/:path*"],
};
