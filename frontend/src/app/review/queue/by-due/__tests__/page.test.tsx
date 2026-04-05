import { render, screen } from "@testing-library/react";
import ReviewQueueByDuePage from "@/app/review/queue/by-due/page";
import { getGroupedReviewQueueByDue } from "@/lib/knowledge-map-client";

jest.mock("@/lib/knowledge-map-client");

describe("ReviewQueueByDuePage", () => {
  const mockGetGroupedReviewQueueByDue = getGroupedReviewQueueByDue as jest.MockedFunction<
    typeof getGroupedReviewQueueByDue
  >;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders learner queue items grouped by due-date labels", async () => {
    mockGetGroupedReviewQueueByDue.mockResolvedValue({
      generated_at: "2026-04-05T09:00:00+00:00",
      total_count: 3,
      groups: [
        {
          group_key: "due_now",
          label: "Due now",
          due_in_days: 0,
          count: 1,
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
          ],
        },
        {
          group_key: "in_2_days",
          label: "In 2 days",
          due_in_days: 2,
          count: 2,
          items: [
            {
              queue_item_id: "queue-2",
              entry_id: "word-2",
              entry_type: "word",
              text: "practice",
              status: "learning",
              next_review_at: "2999-04-07T09:00:00+00:00",
              last_reviewed_at: null,
              success_streak: 0,
              lapse_count: 1,
              times_remembered: 1,
              exposure_count: 2,
              history: [],
              bucket: "3d",
            },
            {
              queue_item_id: "queue-3",
              entry_id: "phrase-1",
              entry_type: "phrase",
              text: "jump the gun",
              status: "learning",
              next_review_at: "2999-04-07T11:00:00+00:00",
              last_reviewed_at: "2026-04-04T09:00:00+00:00",
              success_streak: 4,
              lapse_count: 1,
              times_remembered: 4,
              exposure_count: 5,
              history: [],
              bucket: "3d",
            },
          ],
        },
      ],
    });

    render(<ReviewQueueByDuePage />);

    expect(await screen.findByRole("heading", { name: /review queue by due date/i })).toBeInTheDocument();
    expect(await screen.findByText("3 scheduled review items")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /group by stage/i })).toHaveAttribute(
      "href",
      "/review/queue",
    );
    expect(screen.getByRole("link", { name: /group by due date/i })).toHaveAttribute(
      "href",
      "/review/queue/by-due",
    );
    expect(screen.getByRole("heading", { name: /due now/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /in 2 days/i })).toBeInTheDocument();
    expect(screen.getByText("persistence")).toBeInTheDocument();
    expect(screen.getByText("practice")).toBeInTheDocument();
    expect(screen.getByText("jump the gun")).toBeInTheDocument();
    expect(screen.getAllByText(/srs stage 3d/i)[0]).toBeInTheDocument();
  });
});
