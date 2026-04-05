import { render, screen, waitFor } from "@testing-library/react";
import AdminReviewQueuePage from "@/app/admin/review-queue/page";
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
          { bucket: "due_now", count: 2 },
          { bucket: "tomorrow", count: 1 },
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
    expect(screen.getByRole("heading", { name: /due now/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /tomorrow/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open due now bucket/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/due_now",
    );
    expect(screen.getByRole("link", { name: /start review from due now/i })).toHaveAttribute(
      "href",
      "/review",
    );
    expect(screen.queryByRole("link", { name: /start review from tomorrow/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/target_type:/i)).not.toBeInTheDocument();
  });

  it("renders the effective time override controls for request-scoped inspection", async () => {
    mockFetchJson(
      makeQueueSummaryResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        totalCount: 1,
        groups: [{ bucket: "due_now", count: 1 }],
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
        groups: [{ bucket: "due_now", count: 1 }],
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
    expect(screen.getByRole("link", { name: /open due now bucket/i })).toHaveAttribute(
      "href",
      "/admin/review-queue/due_now?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00",
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
});
