import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import ReviewPage from "@/app/review/page";

jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

jest.mock("@/lib/api-client", () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

describe("ReviewPage", () => {
  const mockPush = jest.fn();
  const mockApiClient = require("@/lib/api-client").apiClient;

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  });

  it("renders start review button", () => {
    render(<ReviewPage />);
    expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
  });

  it("creates session and loads due cards", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValue({ id: "session-123" });
    mockApiClient.get.mockResolvedValue([
      {
        id: "card-1",
        word_id: "word-1",
        meaning_id: "meaning-1",
        card_type: "flashcard",
      },
    ]);

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith("/reviews/sessions");
      expect(mockApiClient.get).toHaveBeenCalledWith("/reviews/due");
    });
  });

  it("displays flashcard with quality buttons", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValue({ id: "session-123" });
    mockApiClient.get.mockResolvedValue([
      {
        id: "card-1",
        word_id: "word-1",
        meaning_id: "meaning-1",
        card_type: "flashcard",
      },
    ]);

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(screen.getByText(/flashcard/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /1/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /5/i })).toBeInTheDocument();
    });
  });

  it("submits quality rating and moves to next card", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValueOnce({ id: "session-123" });
    mockApiClient.get.mockResolvedValue([
      {
        id: "card-1",
        word_id: "word-1",
        meaning_id: "meaning-1",
        card_type: "flashcard",
      },
      {
        id: "card-2",
        word_id: "word-2",
        meaning_id: "meaning-2",
        card_type: "flashcard",
      },
    ]);
    mockApiClient.post.mockResolvedValueOnce({ quality_rating: 4 });

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(screen.getByText(/card 1/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^4$/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith(
        "/reviews/cards/card-1/submit",
        expect.objectContaining({ quality: 4 })
      );
      expect(screen.getByText(/card 2/i)).toBeInTheDocument();
    });
  });

  it("completes session when all cards reviewed", async () => {
    const user = userEvent.setup();
    mockApiClient.post.mockResolvedValueOnce({ id: "session-123" });
    mockApiClient.get.mockResolvedValue([
      {
        id: "card-1",
        word_id: "word-1",
        meaning_id: "meaning-1",
        card_type: "flashcard",
      },
    ]);
    mockApiClient.post.mockResolvedValueOnce({ quality_rating: 5 });
    mockApiClient.post.mockResolvedValueOnce({ completed_at: new Date().toISOString() });

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));
    await waitFor(() => screen.getByRole("button", { name: /^5$/i }));
    await user.click(screen.getByRole("button", { name: /^5$/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith("/reviews/sessions/session-123/complete");
      expect(screen.getByText(/session complete/i)).toBeInTheDocument();
    });
  });
});
