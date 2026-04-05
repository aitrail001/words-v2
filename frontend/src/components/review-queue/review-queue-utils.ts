import type {
  KnowledgeEntryType,
  KnowledgeStatus,
  ReviewQueueBucket,
  ReviewQueueBucketOrder,
  ReviewQueueBucketSort,
} from "@/lib/knowledge-map-client";

export const REVIEW_QUEUE_BUCKET_LABELS: Record<ReviewQueueBucket, string> = {
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

export const REVIEWABLE_BUCKETS: ReviewQueueBucket[] = ["overdue", "due_now"];

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

export function formatReviewQueueTime(
  value: string | null,
  options?: {
    emptyLabel?: string;
    invalidLabel?: string;
  },
): string {
  if (!value) {
    return options?.emptyLabel ?? "Time to be scheduled";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return options?.invalidLabel ?? "Time unavailable";
  }

  return reviewTimeFormatter.format(parsed);
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
