import { render, screen, waitFor } from "@testing-library/react";
import AdminReviewQueuePage from "@/app/admin/review-queue/page";
import { cookies } from "next/headers";

jest.mock("next/headers", () => ({
  cookies: jest.fn(),
}));

function makeQueueResponse(overrides?: {
  effectiveNow?: string;
  totalCount?: number;
  groups?: Array<{
    bucket: string;
    count: number;
    items: Array<Record<string, unknown>>;
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

  it("renders admin-only queue metadata and debug-only fields from the grouped admin API", async () => {
    mockFetchJson(
      makeQueueResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        totalCount: 1,
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
                next_review_at: "2026-10-05T09:00:00+00:00",
                last_reviewed_at: "2026-10-04T09:00:00+00:00",
                target_type: "meaning",
                target_id: "meaning-1",
                recheck_due_at: "2026-10-05T08:30:00+00:00",
                next_due_at: "2026-10-05T09:00:00+00:00",
                last_outcome: "passed",
                relearning: false,
                relearning_trigger: null,
              },
            ],
          },
        ],
      }),
    );

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByRole("heading", { name: /srs queue debug/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/reviews/admin/queue/grouped",
        expect.objectContaining({
          cache: "no-store",
          headers: { Authorization: "Bearer admin-token" },
        }),
      ),
    );
    expect(screen.getByText(/admin-only queue inspection/i)).toBeInTheDocument();
    expect(screen.getByText(/effective time in use/i)).toBeInTheDocument();
    expect(screen.getByText("2026-10-05T09:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /due now/i })).toBeInTheDocument();
    expect(screen.getByText("persistence")).toBeInTheDocument();
    expect(screen.getByText(/target_type: meaning/i)).toBeInTheDocument();
    expect(screen.getByText(/target_id: meaning-1/i)).toBeInTheDocument();
    expect(screen.getByText(/recheck_due_at: 2026-10-05T08:30:00\+00:00/i)).toBeInTheDocument();
    expect(screen.getByText(/next_due_at: 2026-10-05T09:00:00\+00:00/i)).toBeInTheDocument();
    expect(screen.getByText(/last_outcome: passed/i)).toBeInTheDocument();
    expect(screen.getByText(/relearning: no/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open detail for persistence/i })).toHaveAttribute("href", "/word/word-1");
    expect(screen.getByRole("link", { name: /start review for persistence/i })).toHaveAttribute(
      "href",
      "/review?queue_item_id=queue-1",
    );
    expect(screen.queryByText(/prompt_family:/i)).not.toBeInTheDocument();
  });

  it("renders the effective time override controls for request-scoped inspection", async () => {
    mockFetchJson(
      makeQueueResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
        totalCount: 1,
        groups: [
          {
            bucket: "due_now",
            count: 1,
            items: [
              {
                queue_item_id: "queue-2",
                entry_id: "word-2",
                entry_type: "word",
                text: "candidate",
                status: "learning",
                next_review_at: "2026-10-05T09:00:00+00:00",
                last_reviewed_at: null,
                target_type: "meaning",
                target_id: "meaning-2",
                recheck_due_at: null,
                next_due_at: "2026-10-05T09:00:00+00:00",
                last_outcome: null,
                relearning: true,
                relearning_trigger: "failed_review",
              },
            ],
          },
        ],
      }),
    );

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByLabelText(/effective time override/i)).toHaveValue("");
    expect(screen.getByRole("button", { name: /inspect queue/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /use live time/i })).toHaveAttribute("href", "/admin/review-queue");
  });

  it("shows an admin-oriented empty state when no queue items match the selected time", async () => {
    mockFetchJson(makeQueueResponse());

    render(await AdminReviewQueuePage({}));

    expect(await screen.findByText(/no queued review items match this effective time/i)).toBeInTheDocument();
    expect(screen.getByText(/use the override control to inspect future queue states/i)).toBeInTheDocument();
  });

  it("uses the initial effective_now search param on first render", async () => {
    mockFetchJson(
      makeQueueResponse({
        effectiveNow: "2026-10-05T09:00:00+00:00",
      }),
    );

    render(
      await AdminReviewQueuePage({
        searchParams: Promise.resolve({ effective_now: "2026-10-05T09:00:00+00:00" }),
      }),
    );

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "http://localhost:8000/api/reviews/admin/queue/grouped?effective_now=2026-10-05T09%3A00%3A00%2B00%3A00",
        expect.objectContaining({
          headers: { Authorization: "Bearer admin-token" },
        }),
      ),
    );
    expect(screen.getByDisplayValue("2026-10-05T09:00:00+00:00")).toBeInTheDocument();
    expect(screen.getByText("2026-10-05T09:00:00+00:00")).toBeInTheDocument();
  });
});
