import { cookies } from "next/headers";
import Link from "next/link";
import { ReviewQueueSummaryCard } from "@/components/review-queue/review-queue-shared";
import { ACCESS_TOKEN_COOKIE_KEY } from "@/lib/auth-session";
import type { AdminReviewQueueSummaryResponse } from "@/lib/knowledge-map-client";

const API_BASE_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

class AdminQueuePageError extends Error {
  status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

async function fetchAdminReviewQueueSummary(
  effectiveNow?: string,
): Promise<AdminReviewQueueSummaryResponse> {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE_KEY)?.value;
  if (!accessToken) {
    throw new AdminQueuePageError("Missing admin access token.", 401);
  }

  const baseUrl = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  const url = new URL(`${baseUrl}/reviews/admin/queue/summary`);
  if (effectiveNow) {
    url.searchParams.set("effective_now", effectiveNow);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new AdminQueuePageError(`Unable to load admin review queue summary: ${response.status}`, response.status);
  }

  return (await response.json()) as AdminReviewQueueSummaryResponse;
}

export default async function AdminReviewQueuePage({
  searchParams,
}: {
  searchParams?: Promise<{ effective_now?: string }>;
}) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const effectiveNow = resolvedSearchParams.effective_now?.trim() || undefined;

  let queue: AdminReviewQueueSummaryResponse | null = null;
  let error: string | null = null;

  try {
    queue = await fetchAdminReviewQueueSummary(effectiveNow);
  } catch (caught) {
    if (caught instanceof AdminQueuePageError && caught.status === 401) {
      error = "Admin access required. Sign in as an admin account to view the admin review queue.";
    } else {
      error = "Unable to load the admin review queue.";
    }
  }

  const summaryQuery = effectiveNow
    ? { effective_now: effectiveNow }
    : undefined;

  return (
    <main className="mx-auto max-w-[56rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[0.75rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
              Admin Review Queue
            </p>
            <h1 className="mt-1 text-[1.4rem] font-semibold text-[#5b2590]">Admin Review Queue</h1>
            <p className="mt-2 text-sm text-[#7b6795]">
              Admin-only queue inspection for raw SRS queue state and request-scoped effective-time overrides.
            </p>
            {typeof queue?.total_count === "number" ? (
              <p className="mt-2 text-sm text-[#7b6795]">
                {queue.total_count} queued review {queue.total_count === 1 ? "item" : "items"}
              </p>
            ) : null}
          </div>

          <div className="rounded-[0.8rem] border border-[#ede3fb] bg-[#faf7ff] px-3 py-3">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
              Effective time in use
            </p>
            <p className="mt-1 text-sm font-semibold text-[#5a357b]">
              {queue?.debug.effective_now ?? effectiveNow ?? "Live time"}
            </p>
            <p className="mt-2 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
              Generated at
            </p>
            <p className="mt-1 text-sm text-[#6e5a86]">{queue?.generated_at ?? "Unavailable"}</p>
          </div>
        </div>
      </section>

      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <form className="flex flex-col gap-3 md:flex-row md:items-end" method="get">
          <label className="flex-1 text-sm font-semibold text-[#5a357b]">
            Effective time override
            <input
              type="text"
              name="effective_now"
              defaultValue={effectiveNow ?? ""}
              placeholder="2026-10-05T09:00:00+00:00"
              className="mt-2 w-full rounded-[0.8rem] border border-[#d8caec] px-3 py-2 text-sm text-[#472164]"
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              className="rounded-full bg-[#7b32d3] px-4 py-2 text-sm font-semibold text-white"
            >
              Inspect queue
            </button>
            <Link
              href="/admin/review-queue"
              className="rounded-full border border-[#d8caec] px-4 py-2 text-sm font-semibold text-[#684f85]"
            >
              Use live time
            </Link>
          </div>
        </form>
      </section>

      {error ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm font-semibold text-[#a5374a]">{error}</p>
        </section>
      ) : null}

      {!error && queue && queue.groups.length === 0 ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <h2 className="text-[1.15rem] font-semibold text-[#5b2590]">
            No queued review items match this effective time
          </h2>
          <p className="mt-2 text-sm leading-6 text-[#7b6795]">
            Use the override control to inspect future queue states and bucket movement.
          </p>
        </section>
      ) : null}

      {!error && queue
        ? queue.groups.map((group) => (
            <ReviewQueueSummaryCard
              key={group.bucket}
              group={group}
              hrefPrefix="/admin/review-queue"
              queryParams={summaryQuery}
            />
          ))
        : null}
    </main>
  );
}
