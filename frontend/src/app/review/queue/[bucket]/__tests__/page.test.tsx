import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useParams, useSearchParams } from "next/navigation";
import ReviewQueueBucketPage from "@/app/review/queue/[bucket]/page";
import * as reviewQueueShared from "@/components/review-queue/review-queue-shared";
import { getReviewQueueBucketDetail } from "@/lib/knowledge-map-client";

jest.mock("next/navigation", () => ({
  useParams: jest.fn(),
  useSearchParams: jest.fn(),
}));

jest.mock("@/lib/knowledge-map-client");

describe("ReviewQueueBucketPage", () => {
  const mockUseParams = useParams as jest.MockedFunction<typeof useParams>;
  const mockUseSearchParams = useSearchParams as jest.MockedFunction<typeof useSearchParams>;
  const mockGetReviewQueueBucketDetail = getReviewQueueBucketDetail as jest.MockedFunction<
    typeof getReviewQueueBucketDetail
  >;

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseParams.mockReturnValue({ bucket: "1d" } as never);
    mockUseSearchParams.mockReturnValue(new URLSearchParams("sort=text&order=desc") as never);
  });

  it("renders learner bucket detail rows and only exposes start review for due items", async () => {
    mockGetReviewQueueBucketDetail.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      bucket: "1d",
      count: 2,
      sort: "text",
      order: "desc",
      items: [
        {
          queue_item_id: "queue-1",
          entry_id: "word-1",
          entry_type: "word",
          text: "zeta",
          status: "learning",
          next_review_at: "2000-04-05T12:00:00+00:00",
          last_reviewed_at: "2000-04-04T09:00:00+00:00",
          success_streak: 3,
          lapse_count: 1,
          times_remembered: 4,
          exposure_count: 5,
          history: [
            {
              id: "event-1",
              reviewed_at: "2000-04-04T09:00:00+00:00",
              outcome: "correct_tested",
              prompt_type: "entry_to_definition",
              scheduled_by: "recommended",
              scheduled_interval_days: 3,
            },
            {
              id: "event-2",
              reviewed_at: "2000-04-02T09:00:00+00:00",
              outcome: "failed",
              prompt_type: "typed_recall",
              scheduled_by: "manual_override",
              scheduled_interval_days: 1,
            },
          ],
        },
        {
          queue_item_id: "queue-2",
          entry_id: "phrase-2",
          entry_type: "phrase",
          text: "alpha",
          status: "learning",
          next_review_at: "2999-04-05T10:00:00+00:00",
          last_reviewed_at: null,
          success_streak: 0,
          lapse_count: 0,
          times_remembered: 0,
          exposure_count: 0,
          history: [],
        },
      ],
    });

    render(<ReviewQueueBucketPage />);

    await waitFor(() =>
      expect(mockGetReviewQueueBucketDetail).toHaveBeenCalledWith("1d", "text", "desc"),
    );
    expect(await screen.findByRole("heading", { name: /^1d$/i })).toBeInTheDocument();
    expect(screen.getByText("2 items in this bucket")).toBeInTheDocument();
    expect(screen.getByText("zeta")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText(/success streak 3/i)).toBeInTheDocument();
    expect(screen.getByText(/lapses 1/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /show review history for zeta/i }));
    expect(screen.getByText(/entry_to_definition/i)).toBeInTheDocument();
    expect(screen.getByText(/manual override/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open detail for zeta/i })).toHaveAttribute("href", "/word/word-1");
    expect(screen.getByRole("link", { name: /open detail for alpha/i })).toHaveAttribute("href", "/phrase/phrase-2");
    expect(screen.getByRole("link", { name: /start review for zeta/i })).toHaveAttribute(
      "href",
      "/review?queue_item_id=queue-1",
    );
    expect(screen.queryByRole("link", { name: /start review for alpha/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sort by due time/i })).toHaveAttribute(
      "href",
      "/review/queue/1d?sort=next_review_at&order=desc",
    );
    expect(screen.getByRole("link", { name: /ascending order/i })).toHaveAttribute(
      "href",
      "/review/queue/1d?sort=text&order=asc",
    );
  });

  it("rejects unknown learner queue buckets", async () => {
    mockUseParams.mockReturnValue({ bucket: "invalid_bucket" } as never);

    render(<ReviewQueueBucketPage />);

    expect(await screen.findByText(/unknown review bucket/i)).toBeInTheDocument();
    expect(mockGetReviewQueueBucketDetail).not.toHaveBeenCalled();
  });

  it("passes only serializable baseline props into the shared client card", async () => {
    let capturedProps: Record<string, unknown> | null = null;
    const reviewQueueItemCardSpy = jest
      .spyOn(reviewQueueShared, "ReviewQueueItemCard")
      .mockImplementation((props) => {
        capturedProps = props as Record<string, unknown>;
        return <li data-testid="review-queue-item-card">{props.item.text}</li>;
      });

    try {
      mockGetReviewQueueBucketDetail.mockResolvedValue({
        generated_at: "2026-04-05T09:00:00+00:00",
        bucket: "1d",
        count: 1,
        sort: "text",
        order: "desc",
        items: [
          {
            queue_item_id: "queue-1",
            entry_id: "word-1",
            entry_type: "word",
            text: "zeta",
            status: "learning",
            next_review_at: "2000-04-05T12:00:00+00:00",
            last_reviewed_at: "2000-04-04T09:00:00+00:00",
            success_streak: 3,
            lapse_count: 1,
            times_remembered: 4,
            exposure_count: 5,
            history: [],
          },
        ],
      });

      render(<ReviewQueueBucketPage />);

      await waitFor(() => expect(reviewQueueItemCardSpy).toHaveBeenCalledTimes(1));

      expect(capturedProps).toEqual({
        bucket: "1d",
        item: {
          queue_item_id: "queue-1",
          entry_id: "word-1",
          entry_type: "word",
          text: "zeta",
          status: "learning",
          next_review_at: "2000-04-05T12:00:00+00:00",
          last_reviewed_at: "2000-04-04T09:00:00+00:00",
          success_streak: 3,
          lapse_count: 1,
          times_remembered: 4,
          exposure_count: 5,
          history: [],
        },
      });
      expect(Object.keys(capturedProps ?? {}).sort()).toEqual(["bucket", "item"]);
      expect(() => JSON.stringify(capturedProps)).not.toThrow();
      expect(JSON.parse(JSON.stringify(capturedProps))).toEqual(capturedProps);
    } finally {
      reviewQueueItemCardSpy.mockRestore();
    }
  });
});
