import { proxy, config } from "../proxy";
import { ACCESS_TOKEN_COOKIE_KEY } from "@/lib/auth-session";

jest.mock("next/server", () => ({
  NextResponse: {
    next: jest.fn(() => ({ headers: new Headers({ "x-middleware-next": "1" }) })),
    redirect: jest.fn((url: URL) => ({ headers: new Headers({ location: url.toString() }) })),
  },
}));

const buildRequest = (pathname: string, token?: string) =>
  ({
    cookies: {
      get: (key: string) => (key === ACCESS_TOKEN_COOKIE_KEY && token ? { value: token } : undefined),
    },
    nextUrl: {
      pathname,
    },
    url: `http://example.com${pathname}`,
  }) as Parameters<typeof proxy>[0];

describe("proxy", () => {
  it("redirects unauthenticated /lexicon requests to /login", () => {
    const response = proxy(buildRequest("/lexicon"));

    expect(response.headers.get("location")).toBe("http://example.com/login?next=%2Flexicon%2Fops");
  });

  it("allows authenticated requests", () => {
    const response = proxy(buildRequest("/lexicon/ops", "active-token"));

    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("keeps the protected route matcher focused on admin routes", () => {
    expect(config.matcher).toEqual(["/", "/lexicon/:path*"]);
  });
});
