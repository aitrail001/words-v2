import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    logout: jest.fn().mockResolvedValue(undefined),
  },
}));

describe("Admin RootLayout auth navigation", () => {
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    window.localStorage.clear();
    jest.clearAllMocks();
  });

  it("shows login and lexicon links when unauthenticated", () => {
    render(<AuthNavigation />);

    expect(screen.getByTestId("nav-home-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-login-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-lexicon-ops-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-lexicon-voice-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-lexicon-compiled-review-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-lexicon-epub-cache-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-lexicon-import-db-link")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-lexicon-db-inspector-link")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /logout/i }),
    ).not.toBeInTheDocument();
  });

  it("shows logout button when token is present", async () => {
    window.localStorage.setItem("words_admin_access_token", "active-token");

    render(<AuthNavigation />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
    });
  });

  it("calls apiClient.logout from the logout action", async () => {
    window.localStorage.setItem("words_admin_access_token", "active-token");
    const user = userEvent.setup();

    render(<AuthNavigation />);

    const logoutButton = await screen.findByRole("button", { name: /logout/i });
    await user.click(logoutButton);

    expect(mockApiClient.logout).toHaveBeenCalledTimes(1);
  });
});
