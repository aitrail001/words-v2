import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/login/page";
import { apiClient } from "@/lib/api-client";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    post: jest.fn(),
    setTokens: jest.fn(),
  },
}));

describe("LoginPage", () => {
  const mockPost = apiClient.post as jest.MockedFunction<typeof apiClient.post>;
  const mockSetTokens = apiClient.setTokens as jest.MockedFunction<typeof apiClient.setTokens>;
  const assign = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockPost.mockResolvedValue({
      access_token: "access-token",
      refresh_token: "refresh-token",
    });
    mockSetTokens.mockImplementation(() => undefined);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        assign,
        search: "?next=%2Flexicon%2Fcompiled-review",
      },
    });
  });

  it("navigates to the requested path after successful login", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId("login-email-input"), "admin@example.com");
    await user.type(screen.getByTestId("login-password-input"), "password");
    await user.click(screen.getByTestId("login-submit-button"));

    expect(mockPost).toHaveBeenCalledWith("/auth/login", {
      email: "admin@example.com",
      password: "password",
    });
    expect(mockSetTokens).toHaveBeenCalledWith("access-token", "refresh-token");
    expect(assign).toHaveBeenCalledWith("/lexicon/compiled-review");
  });
});
