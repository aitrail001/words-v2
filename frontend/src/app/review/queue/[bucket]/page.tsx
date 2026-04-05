"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ReviewQueueItemCard,
  ReviewQueueSortControls,
} from "@/components/review-queue/review-queue-shared";
import {
  formatReviewQueueBucketLabel,
  isReviewQueueBucket,
  isReviewQueueBucketOrder,
  isReviewQueueBucketSort,
} from "@/components/review-queue/review-queue-utils";
import {
  getReviewQueueBucketDetail,
  type ReviewQueueBucketDetailResponse,
  type ReviewQueueBucketOrder,
  type ReviewQueueBucketSort,
} from "@/lib/knowledge-map-client";

const DEFAULT_SORT: ReviewQueueBucketSort = "next_review_at";
const DEFAULT_ORDER: ReviewQueueBucketOrder = "asc";

export default function ReviewQueueBucketPage() {
  const params = useParams<{ bucket: string }>();
  const searchParams = useSearchParams();
  const rawBucket = Array.isArray(params?.bucket) ? params.bucket[0] : params?.bucket;
  const bucket = isReviewQueueBucket(rawBucket) ? rawBucket : null;
  const rawSort = searchParams.get("sort");
  const rawOrder = searchParams.get("order");
  const sort = isReviewQueueBucketSort(rawSort)
    ? rawSort
    : DEFAULT_SORT;
  const order = isReviewQueueBucketOrder(rawOrder)
    ? rawOrder
    : DEFAULT_ORDER;
  const [detail, setDetail] = useState<ReviewQueueBucketDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!bucket) {
      setLoading(false);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    getReviewQueueBucketDetail(bucket, sort, order)
      .then((response) => {
        if (!active) {
          return;
        }
        setDetail(response);
        setLoading(false);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setError("Unable to load this review bucket.");
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [bucket, order, sort]);

  if (!bucket) {
    return (
      <main className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#472164]">
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <h1 className="text-[1.15rem] font-semibold text-[#5b2590]">Unknown review bucket</h1>
          <p className="mt-2 text-sm leading-6 text-[#7b6795]">
            This review bucket is not available.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/review/queue" className="text-sm font-semibold text-[#7b32d3]">
            Back to queue summary
          </Link>
          <Link href="/" className="text-sm font-semibold text-[#684f85]">
            Back to Home
          </Link>
        </div>
        <h1 className="mt-2 text-[1.4rem] font-semibold text-[#5b2590]">
          {formatReviewQueueBucketLabel(bucket)}
        </h1>
        {!loading && detail ? (
          <p className="mt-2 text-sm text-[#7b6795]">
            {detail.count} {detail.count === 1 ? "item" : "items"} in this bucket
          </p>
        ) : null}
      </section>

      <ReviewQueueSortControls
        bucket={bucket}
        hrefPrefix="/review/queue"
        sort={sort}
        order={order}
      />

      {loading ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm text-[#7b6795]">Loading review bucket…</p>
        </section>
      ) : null}

      {error ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm font-semibold text-[#a5374a]">{error}</p>
        </section>
      ) : null}

      {!loading && !error && detail && detail.items.length === 0 ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm leading-6 text-[#7b6795]">
            No items are currently scheduled in this bucket.
          </p>
        </section>
      ) : null}

      {!loading && !error && detail && detail.items.length > 0 ? (
        <ul className="space-y-3">
          {detail.items.map((item) => (
            <ReviewQueueItemCard key={item.queue_item_id} item={item} bucket={bucket} />
          ))}
        </ul>
      ) : null}
    </main>
  );
}
