import { render, screen } from "@testing-library/react";
import ReviewQueuePage from "@/app/review/queue/page";
import { getReviewQueueSummary } from "@/lib/knowledge-map-client";

jest.mock("@/lib/knowledge-map-client");

describe("ReviewQueuePage", () => {
  const mockGetReviewQueueSummary = getReviewQueueSummary as jest.MockedFunction<
    typeof getReviewQueueSummary
  >;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders learner queue summary cards with bucket detail links", async () => {
    mockGetReviewQueueSummary.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 3,
      groups: [
        { bucket: "overdue", count: 2 },
        { bucket: "tomorrow", count: 1 },
      ],
    });

    render(<ReviewQueuePage />);

    expect(await screen.findByRole("heading", { name: /review queue/i })).toBeInTheDocument();
    expect(await screen.findByText("3 scheduled review items")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to home/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("heading", { name: /overdue/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /tomorrow/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open overdue bucket/i })).toHaveAttribute(
      "href",
      "/review/queue/overdue",
    );
    expect(screen.getByRole("link", { name: /open tomorrow bucket/i })).toHaveAttribute(
      "href",
      "/review/queue/tomorrow",
    );
    expect(screen.getByRole("link", { name: /start review from overdue/i })).toHaveAttribute(
      "href",
      "/review",
    );
    expect(screen.queryByRole("link", { name: /start review from tomorrow/i })).not.toBeInTheDocument();
    expect(screen.queryByText("persistence")).not.toBeInTheDocument();
  });

  it("shows a learner-friendly empty state when there are no queued review items", async () => {
    mockGetReviewQueueSummary.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 0,
      groups: [],
    });

    render(<ReviewQueuePage />);

    expect(await screen.findByText(/your review queue is clear/i)).toBeInTheDocument();
    expect(screen.getByText(/new review work will appear here/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open .* bucket/i })).not.toBeInTheDocument();
  });

  it("does not show a misleading zero-count header while loading", () => {
    mockGetReviewQueueSummary.mockImplementation(() => new Promise(() => {}));

    render(<ReviewQueuePage />);

    expect(screen.getAllByText(/loading your review queue/i)).toHaveLength(2);
    expect(screen.queryByText(/0 scheduled review items/i)).not.toBeInTheDocument();
  });
});
