import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import RegisterPage from "@/app/register/page";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    post: jest.fn(),
    setToken: jest.fn(),
  },
}));

describe("RegisterPage", () => {
  const mockPush = jest.fn();
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  });

  it("renders register form", () => {
    render(<RegisterPage />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /register/i })).toBeInTheDocument();
  });

  it("submits registration and redirects on success", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValue({
      access_token: "test-token",
      email: "new@example.com",
    });

    render(<RegisterPage />);

    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith("/auth/register", {
        email: "new@example.com",
        password: "password123",
      });
      expect(mockApiClient.setToken).toHaveBeenCalledWith("test-token");
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("shows error on registration failure", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockRejectedValue({
      message: "Email already registered",
    });

    render(<RegisterPage />);

    await user.type(screen.getByLabelText(/email/i), "existing@example.com");
    await user.type(screen.getByLabelText(/password/i), "password123");
    await user.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => {
      expect(screen.getByText(/email already registered/i)).toBeInTheDocument();
    });
  });
});
