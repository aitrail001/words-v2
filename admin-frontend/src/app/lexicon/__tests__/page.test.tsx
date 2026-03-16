import { render, screen } from "@testing-library/react";
import LexiconPage from "@/app/lexicon/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";

describe("LexiconPage", () => {
  it("shows landing links for words, operations, and legacy review", () => {
    render(<LexiconPage />);

    expect(screen.getByTestId("lexicon-landing-page")).toBeInTheDocument();
    expect(screen.getByTestId("lexicon-landing-words-link")).toHaveAttribute("href", "/lexicon/words");
    expect(screen.getByTestId("lexicon-landing-ops-link")).toHaveAttribute("href", "/lexicon/ops");
    expect(screen.getByTestId("lexicon-landing-review-link")).toHaveAttribute("href", "/lexicon/review");
    expect(screen.getByText(/legacy review/i)).toBeInTheDocument();
  });
});

describe("Admin auth middleware for /lexicon", () => {
  it("redirects unauthenticated lexicon route requests to /login", () => {
    expect(getAuthRedirectPath("/lexicon", false)).toBe("/login?next=%2Flexicon");
  });

  it("allows authenticated lexicon route requests", () => {
    expect(getAuthRedirectPath("/lexicon", true)).toBeNull();
  });
});
