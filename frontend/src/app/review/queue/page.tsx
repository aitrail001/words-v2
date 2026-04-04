"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getGroupedReviewQueue,
  type GroupedReviewQueueResponse,
  type KnowledgeEntryType,
  type KnowledgeStatus,
  type ReviewQueueBucket,
} from "@/lib/knowledge-map-client";

const BUCKET_LABELS: Record<ReviewQueueBucket, string> = {
  overdue: "Overdue",
  due_now: "Due now",
  later_today: "Later today",
  tomorrow: "Tomorrow",
  this_week: "This week",
  this_month: "This month",
  one_to_three_months: "1-3 months",
  three_to_six_months: "3-6 months",
  six_plus_months: "6+ months",
};

const ENTRY_TYPE_LABELS: Record<KnowledgeEntryType, string> = {
  word: "Word",
  phrase: "Phrase",
};

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "To learn",
  learning: "Learning",
  known: "Known",
};

const REVIEWABLE_BUCKETS: ReviewQueueBucket[] = ["overdue", "due_now"];

const reviewTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

function formatBucketLabel(bucket: ReviewQueueBucket): string {
  return BUCKET_LABELS[bucket] ?? bucket.replaceAll("_", " ");
}

function formatReviewTime(value: string | null): string {
  if (!value) {
    return "Time to be scheduled";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Time unavailable";
  }

  return reviewTimeFormatter.format(parsed);
}

function formatStatusLabel(status: KnowledgeStatus): string {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<GroupedReviewQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    getGroupedReviewQueue()
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
          {hasDueItems ? (
            <Link
              href="/review"
              className="rounded-full bg-[#7b32d3] px-4 py-2 text-sm font-semibold text-white"
            >
              Start Review
            </Link>
          ) : null}
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
            <section
              key={group.bucket}
              className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]"
            >
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-[1.2rem] font-semibold text-[#5b2590]">
                  {formatBucketLabel(group.bucket)}
                </h2>
                <p className="text-sm font-semibold text-[#7b6795]">
                  {group.count} {group.count === 1 ? "item" : "items"}
                </p>
              </div>

              <ul className="mt-4 space-y-3">
                {group.items.map((item) => {
                  const canStartReview = REVIEWABLE_BUCKETS.includes(group.bucket);

                  return (
                  <li
                    key={item.queue_item_id}
                    className="rounded-[0.8rem] border border-[#ece1f7] bg-[#faf7ff] px-3 py-3"
                  >
                    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-base font-semibold text-[#5a357b]">{item.text}</p>
                          <span className="rounded-full bg-[#ede3fb] px-2 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#7b32d3]">
                            {ENTRY_TYPE_LABELS[item.entry_type]}
                          </span>
                          <span className="rounded-full bg-[#dff7fb] px-2 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#1e8aa2]">
                            {formatStatusLabel(item.status)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm text-[#7b6795]">
                          Next review {formatReviewTime(item.next_review_at)}
                        </p>
                        {item.last_reviewed_at ? (
                          <p className="mt-1 text-sm text-[#8f7ba8]">
                            Last reviewed {formatReviewTime(item.last_reviewed_at)}
                          </p>
                        ) : null}
                      </div>

                      <div className="flex flex-wrap gap-2">
                        <Link
                          href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
                          aria-label={`Open detail for ${item.text}`}
                          className="rounded-full border border-[#d8caec] px-3 py-2 text-sm font-semibold text-[#684f85]"
                        >
                          Open detail
                        </Link>
                        {canStartReview ? (
                          <Link
                            href={`/review?queue_item_id=${encodeURIComponent(item.queue_item_id)}`}
                            aria-label={`Start review for ${item.text}`}
                            className="rounded-full bg-[#7b32d3] px-3 py-2 text-sm font-semibold text-white"
                          >
                            Start review
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </li>
                  );
                })}
              </ul>
            </section>
          ))
        : null}
    </main>
  );
}
