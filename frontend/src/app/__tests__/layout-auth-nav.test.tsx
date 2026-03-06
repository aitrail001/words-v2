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

describe("RootLayout auth navigation", () => {
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    window.localStorage.clear();
    jest.clearAllMocks();
  });

  it("shows login and register links when unauthenticated", () => {
    render(<AuthNavigation />);

    expect(screen.getByTestId("nav-login-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-register-link")).toBeInTheDocument();
    expect(screen.getByTestId("nav-imports-link")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /logout/i }),
    ).not.toBeInTheDocument();
  });

  it("shows logout button when token is present", async () => {
    window.localStorage.setItem("words_access_token", "active-token");

    render(<AuthNavigation />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
    });

    expect(screen.queryByTestId("nav-login-link")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-register-link")).not.toBeInTheDocument();
  });

  it("calls apiClient.logout from the logout action", async () => {
    window.localStorage.setItem("words_access_token", "active-token");
    const user = userEvent.setup();

    render(<AuthNavigation />);

    const logoutButton = await screen.findByRole("button", { name: /logout/i });
    await user.click(logoutButton);

    expect(mockApiClient.logout).toHaveBeenCalledTimes(1);
  });
});
