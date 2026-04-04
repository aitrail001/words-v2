import { render, screen } from "@testing-library/react";
import ReviewQueuePage from "@/app/review/queue/page";
import { getGroupedReviewQueue } from "@/lib/knowledge-map-client";

jest.mock("@/lib/knowledge-map-client");

describe("ReviewQueuePage", () => {
  const mockGetGroupedReviewQueue = getGroupedReviewQueue as jest.MockedFunction<typeof getGroupedReviewQueue>;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders grouped learner queue buckets and queue item actions", async () => {
    mockGetGroupedReviewQueue.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 2,
      groups: [
        {
          bucket: "due_now",
          count: 1,
          items: [
            {
              queue_item_id: "queue-1",
              entry_id: "word-1",
              entry_type: "word",
              text: "persistence",
              status: "learning",
              next_review_at: "2026-04-05T09:00:00+00:00",
              last_reviewed_at: "2026-04-04T09:00:00+00:00",
            },
          ],
        },
        {
          bucket: "tomorrow",
          count: 1,
          items: [
            {
              queue_item_id: "queue-2",
              entry_id: "phrase-2",
              entry_type: "phrase",
              text: "carry on",
              status: "learning",
              next_review_at: "2026-04-06T09:00:00+00:00",
              last_reviewed_at: null,
            },
          ],
        },
      ],
    });

    render(<ReviewQueuePage />);

    expect(await screen.findByRole("heading", { name: /review queue/i })).toBeInTheDocument();
    expect(await screen.findByText("2 scheduled review items")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /due now/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /tomorrow/i })).toBeInTheDocument();
    expect(screen.getByText("persistence")).toBeInTheDocument();
    expect(screen.getByText("carry on")).toBeInTheDocument();
    expect(screen.getAllByText("Learning")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /open detail for persistence/i })).toHaveAttribute("href", "/word/word-1");
    expect(screen.getByRole("link", { name: /open detail for carry on/i })).toHaveAttribute("href", "/phrase/phrase-2");
    expect(screen.getByRole("link", { name: /start review for persistence/i })).toHaveAttribute(
      "href",
      "/review?queue_item_id=queue-1",
    );
    expect(screen.queryByRole("link", { name: /start review for carry on/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/last_outcome/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/recheck_due_at/i)).not.toBeInTheDocument();
  });

  it("shows a learner-friendly empty state when there are no queued review items", async () => {
    mockGetGroupedReviewQueue.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 0,
      groups: [],
    });

    render(<ReviewQueuePage />);

    expect(await screen.findByText(/your review queue is clear/i)).toBeInTheDocument();
    expect(screen.getByText(/new review work will appear here/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /start review/i })).not.toBeInTheDocument();
  });

  it("does not show a misleading zero-count header while loading", () => {
    mockGetGroupedReviewQueue.mockImplementation(() => new Promise(() => {}));

    render(<ReviewQueuePage />);

    expect(screen.getAllByText(/loading your review queue/i)).toHaveLength(2);
    expect(screen.queryByText(/0 scheduled review items/i)).not.toBeInTheDocument();
  });
});
