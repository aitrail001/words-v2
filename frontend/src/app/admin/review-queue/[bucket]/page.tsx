import { cookies } from "next/headers";
import Link from "next/link";
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
import { ACCESS_TOKEN_COOKIE_KEY } from "@/lib/auth-session";
import type {
  AdminReviewQueueBucketDetailResponse,
  AdminReviewQueueItem,
  ReviewQueueBucketOrder,
  ReviewQueueBucketSort,
} from "@/lib/knowledge-map-client";

const API_BASE_URL = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const DEFAULT_SORT: ReviewQueueBucketSort = "next_review_at";
const DEFAULT_ORDER: ReviewQueueBucketOrder = "asc";

class AdminQueuePageError extends Error {
  status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

function buildAdminSupplementalFields(item: AdminReviewQueueItem) {
  const fields: Array<{ label: string; value: boolean | string | null | undefined }> = [
    { label: "target_type", value: item.target_type },
    { label: "target_id", value: item.target_id },
    { label: "last_outcome", value: item.last_outcome },
    { label: "relearning", value: item.relearning },
    { label: "relearning_trigger", value: item.relearning_trigger },
  ];

  if (item.recheck_due_at) {
    fields.splice(2, 0, { label: "recheck_due_at", value: item.recheck_due_at });
  }

  return fields;
}

async function fetchAdminReviewQueueBucketDetail(
  bucket: string,
  options?: {
    effectiveNow?: string;
    sort?: ReviewQueueBucketSort;
    order?: ReviewQueueBucketOrder;
  },
): Promise<AdminReviewQueueBucketDetailResponse> {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_TOKEN_COOKIE_KEY)?.value;
  if (!accessToken) {
    throw new AdminQueuePageError("Missing admin access token.", 401);
  }

  const baseUrl = API_BASE_URL.endsWith("/") ? API_BASE_URL.slice(0, -1) : API_BASE_URL;
  const url = new URL(`${baseUrl}/reviews/admin/queue/buckets/${bucket}`);
  if (options?.effectiveNow) {
    url.searchParams.set("effective_now", options.effectiveNow);
  }
  url.searchParams.set("sort", options?.sort ?? DEFAULT_SORT);
  url.searchParams.set("order", options?.order ?? DEFAULT_ORDER);

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new AdminQueuePageError(`Unable to load admin review bucket: ${response.status}`, response.status);
  }

  return (await response.json()) as AdminReviewQueueBucketDetailResponse;
}

export default async function AdminReviewQueueBucketPage({
  params,
  searchParams,
}: {
  params: Promise<{ bucket: string }>;
  searchParams?: Promise<{ effective_now?: string; sort?: string; order?: string }>;
}) {
  const resolvedParams = await params;
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const bucket = isReviewQueueBucket(resolvedParams.bucket) ? resolvedParams.bucket : null;
  const effectiveNow = resolvedSearchParams.effective_now?.trim() || undefined;
  const sort = isReviewQueueBucketSort(resolvedSearchParams.sort)
    ? resolvedSearchParams.sort
    : DEFAULT_SORT;
  const order = isReviewQueueBucketOrder(resolvedSearchParams.order)
    ? resolvedSearchParams.order
    : DEFAULT_ORDER;

  if (!bucket) {
    return (
      <main className="mx-auto max-w-[56rem] space-y-4 pb-10 text-[#472164]">
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <h1 className="text-[1.15rem] font-semibold text-[#5b2590]">Unknown review bucket</h1>
          <p className="mt-2 text-sm leading-6 text-[#7b6795]">
            This admin review bucket is not available.
          </p>
        </section>
      </main>
    );
  }

  let detail: AdminReviewQueueBucketDetailResponse | null = null;
  let error: string | null = null;

  try {
    detail = await fetchAdminReviewQueueBucketDetail(bucket, {
      effectiveNow,
      sort,
      order,
    });
  } catch (caught) {
    if (caught instanceof AdminQueuePageError && caught.status === 401) {
      error = "Admin access required. Sign in as an admin account to inspect this review bucket.";
    } else {
      error = "Unable to load the admin review bucket.";
    }
  }

  return (
    <main className="mx-auto max-w-[56rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <Link
              href={effectiveNow ? `/admin/review-queue?effective_now=${encodeURIComponent(effectiveNow)}` : "/admin/review-queue"}
              className="text-sm font-semibold text-[#7b32d3]"
            >
              Back to queue summary
            </Link>
            <h1 className="mt-2 text-[1.4rem] font-semibold text-[#5b2590]">
              {formatReviewQueueBucketLabel(bucket)}
            </h1>
            {detail ? (
              <p className="mt-2 text-sm text-[#7b6795]">
                {detail.count} {detail.count === 1 ? "item" : "items"} in this bucket
              </p>
            ) : null}
          </div>

          <div className="rounded-[0.8rem] border border-[#ede3fb] bg-[#faf7ff] px-3 py-3">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
              Effective time in use
            </p>
            <p className="mt-1 text-sm font-semibold text-[#5a357b]">
              {detail?.debug.effective_now ?? effectiveNow ?? "Live time"}
            </p>
          </div>
        </div>
      </section>

      <ReviewQueueSortControls
        bucket={bucket}
        hrefPrefix="/admin/review-queue"
        sort={sort}
        order={order}
        queryParams={effectiveNow ? { effective_now: effectiveNow } : undefined}
      />

      {error ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm font-semibold text-[#a5374a]">{error}</p>
        </section>
      ) : null}

      {!error && detail && detail.items.length === 0 ? (
        <section className="rounded-[0.9rem] bg-white px-4 py-5 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
          <p className="text-sm leading-6 text-[#7b6795]">
            No items are currently scheduled in this bucket.
          </p>
        </section>
      ) : null}

      {!error && detail && detail.items.length > 0 ? (
        <ul className="space-y-3">
          {detail.items.map((item) => (
            <ReviewQueueItemCard
              key={item.queue_item_id}
              item={item}
              bucket={bucket}
              allowStartReview={false}
              supplementalFields={buildAdminSupplementalFields(item)}
            />
          ))}
        </ul>
      ) : null}
    </main>
  );
}
