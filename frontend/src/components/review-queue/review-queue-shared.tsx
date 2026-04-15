"use client";

import Link from "next/link";
import { useState } from "react";
import {
  REVIEWABLE_BUCKETS,
  REVIEW_QUEUE_ORDER_OPTIONS,
  REVIEW_QUEUE_SORT_OPTIONS,
  formatReviewQueueBucketLabel,
  formatReviewQueueDueLabel,
  formatReviewQueueEntryType,
  formatReviewQueueStatus,
  formatReviewQueueTime,
  getReviewQueueEntryHref,
  isReviewQueueItemDueNow,
} from "@/components/review-queue/review-queue-utils";
import type {
  AdminReviewQueueItem,
  ReviewQueueBucket,
  ReviewQueueBucketOrder,
  ReviewQueueBucketSort,
  ReviewQueueHistoryEvent,
  ReviewQueueItem,
  ReviewQueueSummaryBucket,
} from "@/lib/knowledge-map-client";

type ReviewQueueSupplementalField = {
  label: string;
  value: boolean | string | null | undefined;
};

function buildQueryString(params?: Record<string, string | undefined>): string {
  const searchParams = new URLSearchParams();

  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (!value) {
      return;
    }
    searchParams.set(key, value);
  });

  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

function buildBucketHref(
  prefix: "/review/queue" | "/admin/review-queue",
  bucket: ReviewQueueBucket,
  queryParams?: Record<string, string | undefined>,
): string {
  return `${prefix}/${bucket}${buildQueryString(queryParams)}`;
}

function renderDebugValue(value: boolean | string | null | undefined): string {
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (value === null || value === undefined || value === "") {
    return "none";
  }
  return value;
}

function isSuccessfulOutcome(outcome: string): boolean {
  return ["correct_tested", "remember"].includes(outcome);
}

function formatOutcomeLabel(outcome: string): string {
  return outcome.replaceAll("_", " ");
}

function formatScheduleSourceLabel(value: string | null | undefined): string {
  if (value === "manual_override") {
    return "Manual override";
  }
  if (value === "recommended") {
    return "Algorithm";
  }
  if (!value) {
    return "Unspecified";
  }
  return value.replaceAll("_", " ");
}

function formatIntervalLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) {
    return "Not scheduled";
  }
  if (days === 0) {
    return "Same day";
  }
  if (days === 1) {
    return "1 day";
  }
  return `${days} days`;
}

function ReviewHistoryMiniBar({ history }: { history: ReviewQueueHistoryEvent[] }) {
  const recent = history.slice(0, 12);
  if (recent.length === 0) {
    return <p className="text-sm text-[#8f7ba8]">No review events yet.</p>;
  }

  return (
    <div className="flex flex-wrap items-center gap-1" aria-label="Recent review outcomes">
      {recent.map((event) => (
        <span
          key={event.id}
          title={`${formatOutcomeLabel(event.outcome)} at ${formatReviewQueueTime(event.reviewed_at)}`}
          className={`h-2.5 w-2.5 rounded-[0.2rem] ${
            isSuccessfulOutcome(event.outcome)
              ? "bg-[#45c5dd]"
              : event.outcome === "failed" || event.outcome === "lookup"
                ? "bg-[#ff8a65]"
                : "bg-[#cbbfe0]"
          }`}
        />
      ))}
    </div>
  );
}

export function ReviewQueueModeSwitch({
  mode,
}: {
  mode: "stage" | "due";
}) {
  const options = [
    {
      href: "/review/queue",
      label: "Group by stage",
      active: mode === "stage",
    },
    {
      href: "/review/queue/by-due",
      label: "Group by due date",
      active: mode === "due",
    },
  ];

  return (
    <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Link
            key={option.href}
            href={option.href}
            className={`rounded-full px-4 py-2 text-sm font-semibold ${
              option.active
                ? "bg-[#7b32d3] text-white"
                : "border border-[#d8caec] text-[#684f85]"
            }`}
          >
            {option.label}
          </Link>
        ))}
      </div>
    </section>
  );
}

export function ReviewQueueSummaryCard({
  group,
  hrefPrefix,
  queryParams,
}: {
  group: ReviewQueueSummaryBucket;
  hrefPrefix: "/review/queue" | "/admin/review-queue";
  queryParams?: Record<string, string | undefined>;
}) {
  const bucketLabel = formatReviewQueueBucketLabel(group.bucket);

  return (
    <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[1.2rem] font-semibold text-[#5b2590]">{bucketLabel}</h2>
          <p className="mt-1 text-sm text-[#7b6795]">
            {group.count} scheduled review {group.count === 1 ? "item" : "items"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href={buildBucketHref(hrefPrefix, group.bucket, queryParams)}
            aria-label={`Open ${bucketLabel} bucket`}
            className="rounded-full border border-[#d8caec] px-4 py-2 text-sm font-semibold text-[#684f85]"
          >
            Open
          </Link>
          {hrefPrefix === "/review/queue" &&
          group.has_due_now &&
          REVIEWABLE_BUCKETS.includes(group.bucket) ? (
            <Link
              href="/review"
              aria-label={`Start review from ${bucketLabel}`}
              className="rounded-full bg-[#7b32d3] px-4 py-2 text-sm font-semibold text-white"
            >
              Start review
            </Link>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export function ReviewQueueSortControls({
  bucket,
  hrefPrefix,
  sort,
  order,
  queryParams,
}: {
  bucket: ReviewQueueBucket;
  hrefPrefix: "/review/queue" | "/admin/review-queue";
  sort: ReviewQueueBucketSort;
  order: ReviewQueueBucketOrder;
  queryParams?: Record<string, string | undefined>;
}) {
  return (
    <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
            Sort by
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {REVIEW_QUEUE_SORT_OPTIONS.map((option) => (
              <Link
                key={option.value}
                href={buildBucketHref(hrefPrefix, bucket, {
                  ...queryParams,
                  sort: option.value,
                  order,
                })}
                aria-label={`Sort by ${option.label}`}
                className={`rounded-full px-3 py-2 text-sm font-semibold ${
                  option.value === sort
                    ? "bg-[#7b32d3] text-white"
                    : "border border-[#d8caec] text-[#684f85]"
                }`}
              >
                {option.label}
              </Link>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
            Order
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {REVIEW_QUEUE_ORDER_OPTIONS.map((option) => (
              <Link
                key={option.value}
                href={buildBucketHref(hrefPrefix, bucket, {
                  ...queryParams,
                  sort,
                  order: option.value,
                })}
                aria-label={`${option.label} order`}
                className={`rounded-full px-3 py-2 text-sm font-semibold ${
                  option.value === order
                    ? "bg-[#7b32d3] text-white"
                    : "border border-[#d8caec] text-[#684f85]"
                }`}
              >
                {option.label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function ReviewQueueDebugField({
  label,
  value,
}: {
  label: string;
  value: boolean | string | null | undefined;
}) {
  return (
    <p className="text-sm text-[#6e5a86]">
      {label}: {renderDebugValue(value)}
    </p>
  );
}

export function ReviewQueueItemCard({
  item,
  bucket,
  allowStartReview = true,
  showStageLabel = false,
  supplementalFields,
}: {
  item: ReviewQueueItem | AdminReviewQueueItem;
  bucket?: ReviewQueueBucket;
  allowStartReview?: boolean;
  showStageLabel?: boolean;
  supplementalFields?: ReviewQueueSupplementalField[];
}) {
  const resolvedBucket = bucket ?? item.bucket ?? null;
  const exactDueAt = item.min_due_at_utc ?? item.next_review_at;
  const isDueNow = isReviewQueueItemDueNow(exactDueAt);
  const canStartReview =
    allowStartReview &&
    resolvedBucket !== null &&
    REVIEWABLE_BUCKETS.includes(resolvedBucket) &&
    isDueNow;
  const [historyOpen, setHistoryOpen] = useState(false);
  const dueLabel = formatReviewQueueDueLabel(item) ?? "Due now";
  const history = item.history ?? [];
  const successStreak = item.success_streak ?? 0;
  const lapseCount = item.lapse_count ?? 0;
  const timesRemembered = item.times_remembered ?? 0;
  const exposureCount = item.exposure_count ?? 0;

  return (
    <li className="rounded-[0.8rem] border border-[#ece1f7] bg-[#faf7ff] px-3 py-3">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-[#5a357b]">{item.text}</p>
            <span className="rounded-full bg-[#ede3fb] px-2 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#7b32d3]">
              {formatReviewQueueEntryType(item.entry_type)}
            </span>
            <span className="rounded-full bg-[#dff7fb] px-2 py-1 text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#1e8aa2]">
              {formatReviewQueueStatus(item.status)}
            </span>
          </div>
          <p className="mt-2 text-sm text-[#7b6795]">
            <span className="font-semibold text-[#5a357b]">{dueLabel}</span>
            {!isDueNow ? ` · ${formatReviewQueueTime(exactDueAt)}` : ""}
          </p>
          {showStageLabel && resolvedBucket ? (
            <p className="mt-1 text-sm text-[#8f7ba8]">SRS stage {formatReviewQueueBucketLabel(resolvedBucket)}</p>
          ) : null}
          {item.last_reviewed_at ? (
            <p className="mt-1 text-sm text-[#8f7ba8]">
              Last reviewed {formatReviewQueueTime(item.last_reviewed_at)}
            </p>
          ) : null}
          <div className="mt-3 rounded-[0.7rem] border border-[#ede3fb] bg-white px-3 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <p className="text-sm font-semibold text-[#5a357b]">
                Success streak {successStreak}
              </p>
              <p className="text-sm font-semibold text-[#8f7ba8]">
                Lapses {lapseCount}
              </p>
              <p className="text-sm text-[#8f7ba8]">
                Remembered {timesRemembered} / Exposures {exposureCount}
              </p>
            </div>
            <div className="mt-2">
              <ReviewHistoryMiniBar history={history} />
            </div>
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setHistoryOpen((current) => !current)}
                aria-expanded={historyOpen}
                className="text-sm font-semibold text-[#7b32d3]"
              >
                {historyOpen ? "Hide" : "Show"} review history for {item.text}
              </button>
            </div>
            {historyOpen ? (
              <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
                {history.length > 0 ? (
                  history.map((event) => (
                    <div
                      key={event.id}
                      className="rounded-[0.65rem] border border-[#f0e7fb] bg-[#faf7ff] px-3 py-2"
                    >
                      <p className="text-sm font-semibold text-[#5a357b]">
                        {formatOutcomeLabel(event.outcome)}
                      </p>
                      <p className="mt-1 text-sm text-[#7b6795]">
                        {formatReviewQueueTime(event.reviewed_at)}
                      </p>
                      <p className="mt-1 text-sm text-[#8f7ba8]">
                        {event.prompt_type}
                        {event.prompt_family ? ` · ${event.prompt_family}` : ""}
                      </p>
                      <p className="mt-1 text-sm text-[#8f7ba8]">
                        {formatScheduleSourceLabel(event.scheduled_by)} · {formatIntervalLabel(event.scheduled_interval_days)}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-[#8f7ba8]">No review events yet.</p>
                )}
              </div>
            ) : null}
          </div>
          {supplementalFields && supplementalFields.length > 0 ? (
            <div className="mt-3 space-y-1">
              {supplementalFields.map((field) => (
                <ReviewQueueDebugField key={field.label} label={field.label} value={field.value} />
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            href={getReviewQueueEntryHref(item.entry_type, item.entry_id)}
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

export function ReviewQueueGroupedSection({
  title,
  count,
  items,
  bucket,
  showStageLabel = false,
  openHref,
}: {
  title: string;
  count: number;
  items: Array<ReviewQueueItem | AdminReviewQueueItem>;
  bucket?: ReviewQueueBucket;
  showStageLabel?: boolean;
  openHref?: string;
}) {
  return (
    <section className="space-y-3 rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[1.2rem] font-semibold text-[#5b2590]">{title}</h2>
          <p className="mt-1 text-sm text-[#7b6795]">
            {count} {count === 1 ? "item" : "items"} in this group
          </p>
        </div>
        {openHref ? (
          <Link
            href={openHref}
            aria-label={`Open ${title} bucket`}
            className="rounded-full border border-[#d8caec] px-4 py-2 text-sm font-semibold text-[#684f85]"
          >
            Open
          </Link>
        ) : null}
      </div>
      <ul className="space-y-3">
        {items.map((item) => (
          <ReviewQueueItemCard
            key={item.queue_item_id}
            item={item}
            bucket={bucket}
            showStageLabel={showStageLabel}
          />
        ))}
      </ul>
    </section>
  );
}
