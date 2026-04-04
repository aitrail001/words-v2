import Link from "next/link";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getAdminGroupedReviewQueue,
  type AdminGroupedReviewQueueItem,
  type AdminGroupedReviewQueueResponse,
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

function formatBucketLabel(bucket: ReviewQueueBucket): string {
  return BUCKET_LABELS[bucket] ?? bucket.replaceAll("_", " ");
}

function formatStatusLabel(status: KnowledgeStatus): string {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

function formatDebugValue(value: boolean | string | null | undefined): string {
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (value === null || value === undefined || value === "") {
    return "none";
  }
  return value;
}

function DebugField({
  label,
  value,
}: {
  label: string;
  value: boolean | string | null | undefined;
}) {
  return (
    <p className="text-sm text-[#6e5a86]">
      {label}: {formatDebugValue(value)}
    </p>
  );
}

function QueueItemCard({
  item,
  canStartReview,
}: {
  item: AdminGroupedReviewQueueItem;
  canStartReview: boolean;
}) {
  return (
    <li className="rounded-[0.8rem] border border-[#ece1f7] bg-[#faf7ff] px-3 py-3">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
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

          <div className="mt-3 space-y-1">
            <DebugField label="next_review_at" value={item.next_review_at} />
            <DebugField label="last_reviewed_at" value={item.last_reviewed_at} />
            <DebugField label="target_type" value={item.target_type} />
            <DebugField label="target_id" value={item.target_id} />
            <DebugField label="recheck_due_at" value={item.recheck_due_at} />
            <DebugField label="next_due_at" value={item.next_due_at} />
            <DebugField label="last_outcome" value={item.last_outcome} />
            <DebugField label="relearning" value={item.relearning} />
            <DebugField label="relearning_trigger" value={item.relearning_trigger} />
          </div>
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
}

export default async function AdminReviewQueuePage({
  searchParams,
}: {
  searchParams?: Promise<{ effective_now?: string }>;
}) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const effectiveNow = resolvedSearchParams.effective_now?.trim() || undefined;

  let queue: AdminGroupedReviewQueueResponse | null = null;
  let error: string | null = null;

  try {
    queue = await getAdminGroupedReviewQueue(effectiveNow);
  } catch {
    error = "Unable to load the admin review queue.";
  }

  return (
    <main className="mx-auto max-w-[56rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[0.75rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
              Admin SRS Queue
            </p>
            <h1 className="mt-1 text-[1.4rem] font-semibold text-[#5b2590]">SRS Queue Debug</h1>
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
                {group.items.map((item) => (
                  <QueueItemCard
                    key={item.queue_item_id}
                    item={item}
                    canStartReview={REVIEWABLE_BUCKETS.includes(group.bucket)}
                  />
                ))}
              </ul>
            </section>
          ))
        : null}
    </main>
  );
}
