import { render, screen } from "@testing-library/react";
import AdminHomePage from "@/app/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";
import { AuthNavigation } from "@/lib/auth-nav";

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
  readRefreshToken: jest.fn(() => null),
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

describe("AuthNavigation", () => {
  it("renders the compact top-level lexicon menu", () => {
    render(<AuthNavigation />);

    expect(screen.getByTestId("nav-home-link")).toHaveTextContent("Home");
    expect(screen.getByTestId("nav-lexicon-ops-link")).toHaveTextContent("Lexicon Ops");
    expect(screen.getByTestId("nav-lexicon-voice-link")).toHaveTextContent("Voice");
    expect(screen.getByTestId("nav-lexicon-voice-link")).toHaveAttribute("href", "/lexicon/voice-runs");
    expect(screen.getByTestId("nav-lexicon-compiled-review-link")).toHaveTextContent("Enrichment Review");
    expect(screen.getByTestId("nav-lexicon-epub-cache-link")).toHaveTextContent("EPUB Cache");
    expect(screen.getByTestId("nav-logout-button")).toHaveTextContent("Logout");
    expect(screen.queryByTestId("nav-lexicon-jsonl-review-link")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-lexicon-import-db-link")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-lexicon-db-inspector-link")).not.toBeInTheDocument();
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
