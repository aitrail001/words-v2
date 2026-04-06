import { render, screen } from "@testing-library/react";
import ReviewQueuePage from "@/app/review/queue/page";
import { getGroupedReviewQueue } from "@/lib/knowledge-map-client";
import { ReviewQueueItemCard } from "@/components/review-queue/review-queue-shared";
import { formatReviewQueueDueLabel } from "@/components/review-queue/review-queue-utils";

jest.mock("@/lib/knowledge-map-client");

describe("ReviewQueuePage", () => {
  const mockGetGroupedReviewQueue = getGroupedReviewQueue as jest.MockedFunction<
    typeof getGroupedReviewQueue
  >;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders learner stage-grouped queue items with a mode switch", async () => {
    mockGetGroupedReviewQueue.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 3,
      groups: [
        {
          bucket: "1d",
          count: 2,
          items: [
            {
              queue_item_id: "queue-1",
              entry_id: "word-1",
              entry_type: "word",
              text: "persistence",
              status: "learning",
              next_review_at: null,
              last_reviewed_at: "2026-04-04T09:00:00+00:00",
              success_streak: 2,
              lapse_count: 0,
              times_remembered: 2,
              exposure_count: 3,
              history: [],
              bucket: "1d",
            },
            {
              queue_item_id: "queue-2",
              entry_id: "word-2",
              entry_type: "word",
              text: "practice",
              status: "learning",
              next_review_at: "2999-04-06T09:00:00+00:00",
              last_reviewed_at: null,
              success_streak: 0,
              lapse_count: 1,
              times_remembered: 1,
              exposure_count: 2,
              history: [],
              bucket: "1d",
            },
          ],
        },
        {
          bucket: "7d",
          count: 1,
          items: [
            {
              queue_item_id: "queue-3",
              entry_id: "phrase-1",
              entry_type: "phrase",
              text: "jump the gun",
              status: "learning",
              next_review_at: "2999-04-12T09:00:00+00:00",
              last_reviewed_at: "2026-04-04T09:00:00+00:00",
              success_streak: 4,
              lapse_count: 1,
              times_remembered: 4,
              exposure_count: 5,
              history: [],
              bucket: "7d",
            },
          ],
        },
      ],
    });

    render(<ReviewQueuePage />);

    expect(await screen.findByRole("heading", { name: /review queue/i })).toBeInTheDocument();
    expect(await screen.findByText("3 scheduled review items")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to home/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /group by stage/i })).toHaveAttribute(
      "href",
      "/review/queue",
    );
    expect(screen.getByRole("link", { name: /group by due date/i })).toHaveAttribute(
      "href",
      "/review/queue/by-due",
    );
    expect(screen.getByRole("heading", { name: /^1d$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^7d$/i })).toBeInTheDocument();
    expect(screen.getByText("persistence")).toBeInTheDocument();
    expect(screen.getByText("practice")).toBeInTheDocument();
    expect(screen.getByText("jump the gun")).toBeInTheDocument();
    expect(screen.getAllByText(/srs stage/i)[0]).toBeInTheDocument();
    expect(screen.getAllByText(/due now/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /^start review$/i })).toHaveAttribute(
      "href",
      "/review",
    );
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
    expect(screen.queryByRole("link", { name: /open .* bucket/i })).not.toBeInTheDocument();
  });

  it("does not show a misleading zero-count header while loading", () => {
    mockGetGroupedReviewQueue.mockImplementation(() => new Promise(() => {}));

    render(<ReviewQueuePage />);

    expect(screen.getAllByText(/loading your review queue/i)).toHaveLength(2);
    expect(screen.queryByText(/0 scheduled review items/i)).not.toBeInTheDocument();
  });

  it("renders queue item due labels from due_review_date and min_due_at_utc", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-04-10T16:30:00Z"));

    render(
      <ReviewQueueItemCard
        bucket="tomorrow"
        item={{
          queue_item_id: "queue-1",
          entry_id: "word-1",
          entry_type: "word",
          text: "resilience",
          status: "learning",
          next_review_at: null,
          due_review_date: "2026-04-11",
          min_due_at_utc: "2026-04-10T18:00:00Z",
          last_reviewed_at: "2026-04-09T18:00:00Z",
          success_streak: 2,
          lapse_count: 0,
          times_remembered: 3,
          exposure_count: 4,
          history: [],
        } as never}
      />,
    );

    expect(
      screen.getAllByText((_, node) =>
        Boolean(node?.textContent?.includes("Tomorrow") && node.textContent.includes("4:00 AM")),
      ).length,
    ).toBeGreaterThan(0);
  });

  it("uses an explicit timezone when formatting cutoff-sensitive due labels", () => {
    const item = {
      next_review_at: null,
      due_review_date: "2026-04-10",
      min_due_at_utc: "2026-04-10T12:00:00Z",
    };
    const now = new Date("2026-04-10T10:30:00Z");

    expect(formatReviewQueueDueLabel(item, now, { timeZone: "America/Los_Angeles" })).toBe("Tomorrow");
    expect(formatReviewQueueDueLabel(item, now, { timeZone: "UTC" })).toBe("Later today");
  });
});
