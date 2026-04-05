"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { REVIEWABLE_BUCKETS } from "@/components/review-queue/review-queue-utils";
import {
  ReviewQueueSummaryCard,
} from "@/components/review-queue/review-queue-shared";
import {
  getReviewQueueSummary,
  type ReviewQueueSummaryResponse,
} from "@/lib/knowledge-map-client";

export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<ReviewQueueSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    getReviewQueueSummary()
      .then((response) => {
        if (!active) {
          return;
        }
        setQueue(response);
        setLoading(false);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setError("Unable to load your review queue.");
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const totalCount = queue?.total_count;
  const hasDueItems = Boolean(
    queue?.groups.some((group) => REVIEWABLE_BUCKETS.includes(group.bucket)),
  );

  return (
    <main className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[0.75rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
              Review Queue
            </p>
            <h1 className="mt-1 text-[1.4rem] font-semibold text-[#5b2590]">
              Review Queue
            </h1>
            {typeof totalCount === "number" ? (
              <p className="mt-2 text-sm text-[#7b6795]">
                {totalCount} scheduled review {totalCount === 1 ? "item" : "items"}
              </p>
            ) : (
              <p className="mt-2 text-sm text-[#7b6795]">
                {loading ? "Loading your review queue…" : "Review queue status unavailable"}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/"
              className="rounded-full border border-[#d8caec] px-4 py-2 text-sm font-semibold text-[#684f85]"
            >
              Back to Home
            </Link>
            {hasDueItems ? (
              <Link
                href="/review"
                className="rounded-full bg-[#7b32d3] px-4 py-2 text-sm font-semibold text-white"
              >
                Start Review
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      {loading ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm text-[#7b6795]">Loading your review queue…</p>
        </section>
      ) : null}

      {error ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm font-semibold text-[#a5374a]">{error}</p>
        </section>
      ) : null}

      {!loading && !error && queue && queue.groups.length === 0 ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <h2 className="text-[1.15rem] font-semibold text-[#5b2590]">Your review queue is clear</h2>
          <p className="mt-2 text-sm leading-6 text-[#7b6795]">
            New review work will appear here as your learning schedule fills up.
          </p>
        </section>
      ) : null}

      {!loading && !error && queue
        ? queue.groups.map((group) => (
            <ReviewQueueSummaryCard
              key={group.bucket}
              group={group}
              hrefPrefix="/review/queue"
            />
          ))
        : null}
    </main>
  );
}
