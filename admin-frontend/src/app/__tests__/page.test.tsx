import { render, screen } from "@testing-library/react";
import AdminHomePage from "@/app/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";

jest.mock("next/link", () => {
  const MockLink = ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  );
  MockLink.displayName = "MockLink";
  return MockLink;
});

jest.mock("@/lib/auth-session", () => ({
  readAccessToken: jest.fn(() => "active-token"),
}));

jest.mock("@/lib/auth-redirect", () => ({
  redirectToLogin: jest.fn(),
}));

describe("AdminHomePage", () => {
  it("renders admin dashboard and lexicon ops link", () => {
    render(<AdminHomePage />);

    expect(screen.getByTestId("admin-home-page")).toBeInTheDocument();
    expect(screen.getByText(/Compiled Review as the default review path/i)).toBeInTheDocument();
    expect(screen.getByTestId("admin-home-lexicon-link")).toHaveAttribute(
      "href",
      "/lexicon/ops",
    );
  });
});

describe("Auth middleware", () => {
  it("redirects unauthenticated requests to /login", () => {
    expect(getAuthRedirectPath("/", false)).toBe("/login?next=%2F");
  });

  it("redirects unauthenticated /lexicon requests", () => {
    expect(getAuthRedirectPath("/lexicon", false)).toBe(
      "/login?next=%2Flexicon",
    );
  });

  it("allows authenticated requests", () => {
    expect(getAuthRedirectPath("/lexicon", true)).toBeNull();
  });

  it("does not protect /login", () => {
    expect(getAuthRedirectPath("/login", false)).toBeNull();
  });
});
