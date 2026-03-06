import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import LoginPage from "@/app/login/page";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    post: jest.fn(),
    setTokens: jest.fn(),
  },
}));

describe("LoginPage", () => {
  const mockPush = jest.fn();
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  });

  it("renders login form", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log in/i })).toBeInTheDocument();
  });

  it("submits login and redirects on success", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValue({
      access_token: "test-token",
      refresh_token: "refresh-token",
      email: "test@example.com",
    });

    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "test@example.com");
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith("/auth/login", {
        email: "test@example.com",
        password: "password123",
      });
      expect(mockApiClient.setTokens).toHaveBeenCalledWith(
        "test-token",
        "refresh-token",
      );
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("shows error on login failure", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockRejectedValue({
      message: "Incorrect email or password",
    });

    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email/i), "wrong@example.com");
    await user.type(screen.getByLabelText(/password/i), "wrongpass");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByText(/incorrect email or password/i)).toBeInTheDocument();
    });
  });
});
