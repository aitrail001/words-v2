import type {
  KnowledgeEntryType,
  KnowledgeStatus,
  ReviewQueueBucket,
  ReviewQueueBucketOrder,
  ReviewQueueBucketSort,
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

export function formatReviewQueueStatus(status: KnowledgeStatus): string {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

export function getReviewQueueEntryHref(entryType: KnowledgeEntryType, entryId: string): string {
  return entryType === "phrase" ? `/phrase/${entryId}` : `/word/${entryId}`;
}

export function formatReviewQueueEntryType(entryType: KnowledgeEntryType): string {
  return ENTRY_TYPE_LABELS[entryType];
}
