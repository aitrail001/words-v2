import { render, screen, waitFor } from "@testing-library/react";
import AdminReviewQueuePage from "@/app/admin/review-queue/page";
import AdminReviewQueueBucketPage from "@/app/admin/review-queue/[bucket]/page";
import { cookies } from "next/headers";

jest.mock("next/headers", () => ({
  cookies: jest.fn(),
}));

function makeQueueSummaryResponse(overrides?: {
  effectiveNow?: string;
  totalCount?: number;
  groups?: Array<{
    bucket: string;
    count: number;
  }>;
}) {
  return {
    generated_at: "2026-04-05T09:00:00+00:00",
    total_count: overrides?.totalCount ?? 0,
    groups: overrides?.groups ?? [],
    debug: {
      effective_now: overrides?.effectiveNow ?? "2026-04-05T09:00:00+00:00",
    },
  };
}

describe("AdminReviewQueuePage", () => {
  const mockCookies = cookies as jest.MockedFunction<typeof cookies>;
  const originalFetch = global.fetch;

  const mockFetchJson = (payload: unknown) => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    } as Response);
  };

  beforeEach(() => {
    jest.resetAllMocks();
    mockCookies.mockResolvedValue({
      get: jest.fn().mockReturnValue({ value: "admin-token" }),
    } as never);
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("renders the admin queue summary cards from the shared summary endpoint", async () => {
    mockFetchJson(
      makeQueueSummaryResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        totalCount: 3,
        groups: [
          { bucket: "1d", count: 2, has_due_now: true },
          { bucket: "7d", count: 1, has_due_now: true },
        ],
      }),
    );

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByRole("heading", { name: /admin review queue/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/reviews/admin/queue/summary",
        expect.objectContaining({
          cache: "no-store",
          headers: { Authorization: "Bearer admin-token" },
        }),
      ),
    );
    expect(screen.getByText(/request-scoped effective-time overrides/i)).toBeInTheDocument();
    expect(screen.getByText("2026-10-05T09:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^1d$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^7d$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open 1d bucket/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/1d",
    );
    expect(screen.queryByRole("link", { name: /start review from .* bucket/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/target_type:/i)).not.toBeInTheDocument();
  });

  it("renders the effective time override controls for request-scoped inspection", async () => {
    mockFetchJson(
      makeQueueSummaryResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        totalCount: 1,
        groups: [{ bucket: "1d", count: 1, has_due_now: true }],
      }),
    );

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByLabelText(/effective time override/i)).toHaveValue("");
    expect(screen.getByRole("button", { name: /inspect queue/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /use live time/i })).toHaveAttribute("href", "/admin/review-queue");
  });

  it("shows an admin-oriented empty state when no queue items match the selected time", async () => {
    mockFetchJson(makeQueueSummaryResponse());

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByText(/no queued review items match this effective time/i)).toBeInTheDocument();
    expect(screen.getByText(/use the override control to inspect future queue states/i)).toBeInTheDocument();
  });

  it("uses the initial effective_now search param on first render", async () => {
    mockFetchJson(
      makeQueueSummaryResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        groups: [{ bucket: "1d", count: 1, has_due_now: true }],
      }),
    );

    render(
      await AdminReviewQueuePage({
        searchParams: Promise.resolve({ effective_now: "2026-10-05T09:00:00+00:00" }),
      }),
    );

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/reviews/admin/queue/summary?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00",
        expect.objectContaining({
          headers: { Authorization: "Bearer admin-token" },
        }),
      ),
    );
    expect(screen.getByDisplayValue("2026-10-05T09:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open 1d bucket/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/1d?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00",
    );
  });

  it("shows an explicit admin-access message when the backend returns 401", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
    } as Response);

    render(await AdminReviewQueuePage({}));

    expect(
      await screen.findByText(/admin access required\. sign in as an admin account/i),
    ).toBeInTheDocument();
  });

  it("omits empty admin diagnostics rows on the real admin bucket page", async () => {
    mockFetchJson({
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
          history: [],
          target_type: "meaning",
          target_id: "meaning-1",
          recheck_due_at: null,
          next_due_at: null,
          last_outcome: "correct_tested",
          relearning: false,
          relearning_trigger: null,
        },
      ],
    });

    render(
      await AdminReviewQueueBucketPage({
        params: Promise.resolve({ bucket: "7d" }),
        searchParams: Promise.resolve({}),
      }),
    );

    expect(await screen.findByText("candidate")).toBeInTheDocument();
    expect(screen.getByText(/target_type: meaning/i)).toBeInTheDocument();
    expect(screen.queryByText("next_due_at: none")).not.toBeInTheDocument();
    expect(screen.queryByText("recheck_due_at: none")).not.toBeInTheDocument();
  });
});
