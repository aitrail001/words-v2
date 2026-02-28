import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HomePage from "@/app/page";

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
  },
}));

describe("HomePage (Word Search)", () => {
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders search input", () => {
    render(<HomePage />);
    expect(screen.getByPlaceholderText(/search words/i)).toBeInTheDocument();
  });

  it("searches words and displays results", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([
      { id: "1", word: "bank", language: "en", frequency_rank: 100 },
      { id: "2", word: "banker", language: "en", frequency_rank: 500 },
    ]);

    render(<HomePage />);

    await user.type(screen.getByPlaceholderText(/search words/i), "bank");

    await waitFor(() => {
      expect(mockApiClient.get).toHaveBeenCalledWith("/words/search?q=bank");
      expect(screen.getByText("bank")).toBeInTheDocument();
      expect(screen.getByText("banker")).toBeInTheDocument();
    });
  });

  it("shows no results message when empty", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([]);

    render(<HomePage />);

    await user.type(screen.getByPlaceholderText(/search words/i), "xyz");

    await waitFor(() => {
      expect(screen.getByText(/no words found/i)).toBeInTheDocument();
    });
  });
});
