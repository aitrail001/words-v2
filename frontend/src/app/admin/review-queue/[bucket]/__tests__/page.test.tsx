import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { cookies } from "next/headers";
import AdminReviewQueueBucketPage from "@/app/admin/review-queue/[bucket]/page";

jest.mock("next/headers", () => ({
  cookies: jest.fn(),
}));

describe("AdminReviewQueueBucketPage", () => {
  const mockCookies = cookies as jest.MockedFunction<typeof cookies>;
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.resetAllMocks();
    mockCookies.mockResolvedValue({
      get: jest.fn().mockReturnValue({ value: "admin-token" }),
    } as never);
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders admin bucket detail rows with debug fields and preserved controls", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        generated_at: "2026-10-05T09:00:00+00:00",
        bucket: "7d",
        count: 1,
        sort: "text",
        order: "desc",
        debug: {
          effective_now: "2026-10-05T09:00:00+00:00",
        },
        items: [
          {
            queue_item_id: "queue-1",
            entry_id: "word-1",
            entry_type: "word",
            text: "candidate",
            status: "learning",
            next_review_at: "2026-10-05T09:00:00+00:00",
            last_reviewed_at: "2026-10-04T09:00:00+00:00",
            success_streak: 5,
            lapse_count: 2,
            times_remembered: 6,
            exposure_count: 8,
            history: [
              {
                id: "event-1",
                reviewed_at: "2026-10-04T09:00:00+00:00",
                outcome: "correct_tested",
                prompt_type: "confidence_check",
                scheduled_by: "recommended",
                scheduled_interval_days: 30,
              },
            ],
            target_type: "meaning",
            target_id: "meaning-1",
            recheck_due_at: null,
            next_due_at: "2026-10-05T09:00:00+00:00",
            last_outcome: "correct_tested",
            relearning: false,
            relearning_trigger: null,
          },
        ],
      }),
    } as Response);

    render(
      await AdminReviewQueueBucketPage({
        params: Promise.resolve({ bucket: "7d" }),
        searchParams: Promise.resolve({
          effective_now: "2026-10-05T09:00:00+00:00",
          sort: "text",
          order: "desc",
        }),
      }),
    );

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/reviews/admin/queue/buckets/7d?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00&sort=text&order=desc",
        expect.objectContaining({
          cache: "no-store",
          headers: { Authorization: "Bearer admin-token" },
        }),
      ),
    );
    expect(await screen.findByRole("heading", { name: /^7d$/i })).toBeInTheDocument();
    expect(screen.getByText("1 item in this bucket")).toBeInTheDocument();
    expect(screen.getByText("candidate")).toBeInTheDocument();
    expect(screen.getByText(/success streak 5/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /show review history for candidate/i }));
    expect(screen.getByText(/confidence_check/i)).toBeInTheDocument();
    expect(screen.getByText(/target_type: meaning/i)).toBeInTheDocument();
    expect(screen.getByText(/last_outcome: correct_tested/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /start review for candidate/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /sort by due time/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/7d?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00&sort=next_review_at&order=desc",
    );
    expect(screen.getByRole("link", { name: /ascending order/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/7d?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00&sort=text&order=asc",
    );
  });

  it("shows an explicit admin-access message when the backend returns 401", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
    } as Response);

    render(
      await AdminReviewQueueBucketPage({
        params: Promise.resolve({ bucket: "7d" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(
      await screen.findByText(/admin access required\. sign in as an admin account/i),
    ).toBeInTheDocument();
  });
});
