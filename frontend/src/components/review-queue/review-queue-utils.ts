import type {
  KnowledgeEntryType,
  KnowledgeStatus,
  ReviewQueueBucket,
  ReviewQueueBucketOrder,
  ReviewQueueBucketSort,
  ReviewQueueItem,
} from "@/lib/knowledge-map-client";

export const REVIEW_QUEUE_BUCKET_LABELS: Record<ReviewQueueBucket, string> = {
  "1d": "1d",
  "2d": "2d",
  "3d": "3d",
  "5d": "5d",
  "7d": "7d",
  "14d": "14d",
  "30d": "30d",
  "90d": "90d",
  "180d": "180d",
};

export const REVIEWABLE_BUCKETS: ReviewQueueBucket[] = [
  "1d",
  "2d",
  "3d",
  "5d",
  "7d",
  "14d",
  "30d",
  "90d",
  "180d",
];

export const REVIEW_QUEUE_SORT_OPTIONS: Array<{ value: ReviewQueueBucketSort; label: string }> = [
  { value: "next_review_at", label: "Due time" },
  { value: "last_reviewed_at", label: "Last reviewed" },
  { value: "text", label: "A-Z" },
];

export const REVIEW_QUEUE_ORDER_OPTIONS: Array<{ value: ReviewQueueBucketOrder; label: string }> = [
  { value: "asc", label: "Ascending" },
  { value: "desc", label: "Descending" },
];

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

const reviewTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const REVIEW_DAY_RELEASE_HOUR_LOCAL = 4;
const DAY_IN_MS = 24 * 60 * 60 * 1000;

export function isReviewQueueBucket(value: string | null | undefined): value is ReviewQueueBucket {
  if (!value) {
    return false;
  }

  return value in REVIEW_QUEUE_BUCKET_LABELS;
}

export function isReviewQueueBucketSort(
  value: string | null | undefined,
): value is ReviewQueueBucketSort {
  return REVIEW_QUEUE_SORT_OPTIONS.some((option) => option.value === value);
}

export function isReviewQueueBucketOrder(
  value: string | null | undefined,
): value is ReviewQueueBucketOrder {
  return REVIEW_QUEUE_ORDER_OPTIONS.some((option) => option.value === value);
}

export function formatReviewQueueBucketLabel(bucket: ReviewQueueBucket): string {
  return REVIEW_QUEUE_BUCKET_LABELS[bucket] ?? bucket.replaceAll("_", " ");
}

function normalizeReviewQueueDate(value: string | null): Date | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed;
}

export function formatReviewQueueTime(
  value: string | null,
  options?: {
    emptyLabel?: string;
    invalidLabel?: string;
  },
): string {
  const parsed = normalizeReviewQueueDate(value);
  if (!parsed) {
    return options?.emptyLabel ?? "Time to be scheduled";
  }

  return reviewTimeFormatter.format(parsed);
}

export function isReviewQueueItemDueNow(value: string | null): boolean {
  const parsed = normalizeReviewQueueDate(value);
  if (!parsed) {
    return true;
  }
  return parsed.getTime() <= Date.now();
}

export function formatReviewQueueDueLabel(value: string | null): string {
  const parsed = normalizeReviewQueueDate(value);
  if (!parsed) {
    return "Due now";
  }

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDueDay = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const dayDiff = Math.round(
    (startOfDueDay.getTime() - startOfToday.getTime()) / (24 * 60 * 60 * 1000),
  );

  if (dayDiff <= 0) {
    return "Due now";
  }
  if (dayDiff === 1) {
    return "Tomorrow";
  }
  return `In ${dayDiff} days`;
}

function startOfLocalDay(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function parseReviewDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return null;
  }

  const [, year, month, day] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day));
  if (
    parsed.getFullYear() !== Number(year)
    || parsed.getMonth() !== Number(month) - 1
    || parsed.getDate() !== Number(day)
  ) {
    return null;
  }

  return parsed;
}

function parseReviewInstant(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function effectiveLocalReviewDay(value: Date): Date {
  const effectiveDay = startOfLocalDay(value);
  if (value.getHours() < REVIEW_DAY_RELEASE_HOUR_LOCAL) {
    effectiveDay.setDate(effectiveDay.getDate() - 1);
  }
  return effectiveDay;
}

export function formatReviewQueueDueLabel(
  item: Pick<ReviewQueueItem, "due_review_date" | "min_due_at_utc" | "next_review_at">,
  now: Date = new Date(),
): string | null {
  const dueReviewDate = parseReviewDate(item.due_review_date);
  if (!dueReviewDate) {
    return null;
  }

  const exactDueAt = parseReviewInstant(item.min_due_at_utc ?? item.next_review_at);
  const effectiveToday = effectiveLocalReviewDay(now);
  const dayDelta = Math.round(
    (startOfLocalDay(dueReviewDate).getTime() - effectiveToday.getTime()) / DAY_IN_MS,
  );

  if (dayDelta < 0) {
    return "Overdue";
  }
  if (dayDelta === 0) {
    if (exactDueAt && exactDueAt.getTime() <= now.getTime()) {
      return "Due now";
    }
    return "Later today";
  }
  if (dayDelta === 1) {
    return "Tomorrow";
  }
  if (dayDelta < 7) {
    return `In ${dayDelta} days`;
  }
  if (dayDelta < 14) {
    return "In a week";
  }
  if (dayDelta < 21) {
    return "In 2 weeks";
  }
  if (dayDelta < 45) {
    return "In a month";
  }

  return `In ${Math.max(2, Math.round(dayDelta / 30))} months`;
}

export function formatReviewQueueSchedule(
  item: Pick<ReviewQueueItem, "due_review_date" | "min_due_at_utc" | "next_review_at">,
): string {
  const dueLabel = formatReviewQueueDueLabel(item);
  const exactDueAt = item.min_due_at_utc ?? item.next_review_at;
  const exactTime = formatReviewQueueTime(exactDueAt, {
    emptyLabel: dueLabel ? "" : "Time to be scheduled",
  }).trim();

  if (dueLabel && exactTime) {
    return `${dueLabel} · ${exactTime}`;
  }
  if (dueLabel) {
    return dueLabel;
  }
  return exactTime || "Time to be scheduled";
}

export function formatReviewQueueStatus(status: KnowledgeStatus): string {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export function getReviewQueueEntryHref(entryType: KnowledgeEntryType, entryId: string): string {
  return entryType === "phrase" ? `/phrase/${entryId}` : `/word/${entryId}`;
}

export function formatReviewQueueEntryType(entryType: KnowledgeEntryType): string {
  return ENTRY_TYPE_LABELS[entryType];
}
