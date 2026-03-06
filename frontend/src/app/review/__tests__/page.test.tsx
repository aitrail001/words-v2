import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import ReviewPage from "@/app/review/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";

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
  const queueItem = {
    item_id: "queue-item-1",
    card_type: "word_to_definition",
    prompt: {
      word: "bank",
      definition: "A financial institution that manages money.",
    },
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
  });

  it("renders start review button", () => {
    render(<ReviewPage />);
    expect(screen.getByRole("button", { name: /start review/i })).toBeInTheDocument();
  });

  it("loads due queue items when review starts", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([queueItem]);

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(mockApiClient.get).toHaveBeenCalledWith("/reviews/queue/due");
    });

    expect(mockApiClient.post).not.toHaveBeenCalledWith("/reviews/sessions");
  });

  it("displays prompt metadata from due queue item", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([queueItem]);

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(screen.getByText("bank")).toBeInTheDocument();
      expect(
        screen.getByText("A financial institution that manages money.")
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /1/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /5/i })).toBeInTheDocument();
    });
  });

  it("submits rating to queue endpoint and moves to next card", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([
      {
        item_id: "queue-item-1",
        card_type: "word_to_definition",
        prompt: {
          word: "bank",
          definition: "A financial institution that manages money.",
        },
      },
      {
        item_id: "queue-item-2",
        card_type: "word_to_definition",
        prompt: {
          word: "branch",
          definition: "A local office of a larger bank.",
        },
      },
    ]);
    mockApiClient.post.mockResolvedValue({ quality_rating: 4 });

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(screen.getByText(/card 1 of 2/i)).toBeInTheDocument();
      expect(screen.getByText("bank")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^4$/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith(
        "/reviews/queue/queue-item-1/submit",
        expect.objectContaining({ quality: 4 })
      );
      expect(screen.getByText(/card 2 of 2/i)).toBeInTheDocument();
      expect(screen.getByText("branch")).toBeInTheDocument();
    });
  });

  it("shows completion state when all queue items are reviewed", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([queueItem]);
    mockApiClient.post.mockResolvedValue({ quality_rating: 5 });

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));
    await waitFor(() => screen.getByRole("button", { name: /^5$/i }));
    await user.click(screen.getByRole("button", { name: /^5$/i }));

    await waitFor(() => {
      expect(mockApiClient.post).toHaveBeenCalledWith(
        "/reviews/queue/queue-item-1/submit",
        expect.objectContaining({ quality: 5 })
      );
      expect(screen.getByText(/session complete/i)).toBeInTheDocument();
    });
  });

  it("shows no cards due state when queue is empty", async () => {
    const user = userEvent.setup();
    mockApiClient.get.mockResolvedValue([]);

    render(<ReviewPage />);

    await user.click(screen.getByRole("button", { name: /start review/i }));

    await waitFor(() => {
      expect(screen.getByText(/no cards due/i)).toBeInTheDocument();
      expect(
        screen.getByText(/you have no cards to review right now/i)
      ).toBeInTheDocument();
    });
  });
});

describe("Auth middleware for /review", () => {
  it("redirects unauthenticated review route requests to /login", () => {
    expect(getAuthRedirectPath("/review", false)).toBe(
      "/login?next=%2Freview",
    );
  });

  it("allows authenticated review route requests", () => {
    expect(getAuthRedirectPath("/review", true)).toBeNull();
  });
});
