# Admin Compiled Review Bulk Jobs Design

## Goal

Make `Approve All` and other whole-batch review actions safe for very large compiled-review batches by moving them to asynchronous background jobs with progress reporting, while tightening the compiled-review admin tool so it does not fetch, store, or return full-batch payloads unnecessarily.

## Problem Statement

The current compiled-review admin flow has a bad scaling shape for large batches:

1. `POST /api/lexicon-compiled-reviews/batches/{batch_id}/bulk-update` executes synchronously.
2. The response returns every updated review item.
3. The admin frontend stores the full returned item array in React state.
4. The compiled-review item list endpoint returns the full batch item set, which encourages a full-memory UI model.

This worked for small batches but breaks down for snapshots with tens of thousands of rows. The failure mode is slow requests, huge payloads, browser memory pressure, and user-visible failures even when the mutation succeeded.

## Constraints

1. Keep the existing admin workflow intact: import -> review -> export/materialize -> import DB.
2. Preserve the operator affordance of `Approve All`, but make its execution safe for 10k-100k item batches.
3. Reuse the existing `lexicon_jobs` framework instead of inventing a second async job system.
4. Avoid widening this slice into a general redesign of all lexicon admin pages.
5. Keep the initial implementation compatible with current batch/item models and current worker/Celery infrastructure.

## Approaches Considered

### Approach A: Keep synchronous bulk update but return summary only

Pros:
- Smallest API change.
- Removes the worst response-size problem.

Cons:
- Still blocks the request for the full batch mutation.
- Still fragile for very large batches because the work remains request-bound.
- Does not provide progress or cancellation semantics.

### Approach B: Move batch-wide review actions to background jobs using `lexicon_jobs` 

Pros:
- Scales operationally.
- Provides explicit progress reporting.
- Reuses existing queue, polling, and progress fields.
- Cleanly supports `Approve All Pending`, `Reject All Pending`, and future filtered bulk actions.

Cons:
- Requires backend API, worker, and frontend polling changes.
- Requires list/summary refresh strategy changes.

### Approach C: Remove whole-batch actions and force page-by-page review

Pros:
- Simplest technical posture.
- Strongest protection against accidental mass mutation.

Cons:
- Makes the admin tool materially weaker.
- Does not match the operator workflow you want.
- Avoids the actual scaling problem rather than fixing it.

## Recommendation

Use Approach B.

The existing `lexicon_jobs` framework already gives us deduplication, status fields, progress counters, and polling. The right change is to recast compiled-review bulk actions as job submissions and then shrink the compiled-review page into a paginated, page-local UI rather than a whole-batch in-memory UI.

## Target Architecture

### 1. Bulk review actions become lexicon jobs

Add a new lexicon job type:
- `compiled_review_bulk_update`

The request creates a queued job with:
- `batch_id`
- `review_status`
- `decision_reason`
- optional filter scope payload

The worker processes the batch in chunks, updates progress after each chunk, and writes summary counts into `result_payload`.

### 2. Compiled-review list endpoints become page-oriented

The item listing contract should stop implying “load the whole batch.”

Add/reshape list behavior to support:
- `status`
- `search`
- `limit`
- `offset`
- deterministic sort

The response should include:
- `items`
- `total`
- `limit`
- `offset`
- `has_more`

The frontend should only hold the current page slice.

### 3. Batch summary becomes lightweight and independently refreshable

The page should be able to refresh:
- batch counts
- job status
- current page items

independently.

That prevents bulk jobs from forcing a full page reload or a full item refetch.

### 4. Export/materialize remain async-safe

The current materialize flow already uses `lexicon_jobs`. That pattern becomes the standard for expensive admin actions:
- create job
- poll job
- refresh summary/page on completion

This aligns bulk review with the rest of the admin operations model.

## API Design

### New endpoint

`POST /api/lexicon-jobs/compiled-review-bulk-update`

Request:
- `batch_id`
- `review_status`
- `decision_reason`
- optional `scope`:
  - `all_pending`
  - future: `filtered`

Response:
- `202 Accepted`
- returns `LexiconJobResponse`

Reasoning:
- The repo already centralizes async lexicon work under `/api/lexicon-jobs/*`.
- Reusing that namespace keeps jobs discoverable and consistent.

### Existing endpoint changes

#### `GET /api/lexicon-compiled-reviews/batches/{batch_id}/items`

Change from returning `LexiconCompiledReviewItem[]` to a paginated envelope:
- `items`
- `total`
- `limit`
- `offset`
- `has_more`

Accept query parameters:
- `status`
- `search`
- `limit`
- `offset`

#### `POST /api/lexicon-compiled-reviews/batches/{batch_id}/bulk-update`

Deprecate the synchronous batch-wide path from the admin UI.

Implementation options:
- keep the route temporarily but make it reject large-scope synchronous updates, or
- change it into a thin compatibility wrapper that internally creates the async job and returns `202`.

Recommended choice:
- keep the route as a compatibility wrapper in this slice if needed by existing tests/client code, but move the frontend to the new jobs endpoint.

## Backend Processing Design

### Worker behavior

The bulk-update worker should:
1. load the job and mark it running
2. resolve scope to the current pending item ids
3. process in chunks, ordered by `review_priority desc, created_at asc, id asc`
4. update each item using the same decision rules as the single-item mutation path
5. update the parent batch counters after each chunk or at the end using recalculated counts
6. write progress after each chunk:
   - `progress_completed`
   - `progress_total`
   - `progress_current_label`
7. complete with `result_payload`:
   - `batch_id`
   - `review_status`
   - `processed_count`
   - `approved_count`
   - `rejected_count`
   - `pending_count`
   - `failed_count`
   - `scope`

### Chunking

Initial chunk size recommendation:
- `500`

That is small enough to keep transactions bounded and large enough to avoid chatty progress updates.

### Failure semantics

If some rows fail, the job should finish as `failed` only for unrecoverable job-level failure.

For row-level issues, prefer:
- continue processing
- count failures in `result_payload`
- surface `completed_with_errors` only if the existing job model is extended later

In this slice, keep the job status model unchanged and treat unexpected exceptions as job failure.

## Frontend Design

### Bulk action UX

`Approve All`, `Reject All`, and `Reopen All` become:
- confirmation modal
- submit async job
- close modal
- show progress card/toast inline

Progress display:
- `11 / 100000 processed`
- current operation label if available
- final success/failure message

### Page state model

Replace whole-batch `items` state with page state:
- `items`
- `totalItems`
- `pageSize`
- `pageOffset`
- `hasMore`
- `statusFilter`
- `search`

After single-item update:
- patch the item in the local page
- refresh batch summary only if needed

After bulk job completion:
- refresh batch summary
- refresh current page only
- keep current filters and page position

### Performance posture

The admin page should never call `setItems(allRows)` for a large batch.

The page should render only the current page slice and rely on server-side pagination/filtering.

## Testing Strategy

### Backend

1. API test: creating a compiled-review bulk job returns `202` and enqueues the correct job type.
2. Worker test: bulk-update job processes pending items and updates progress/result payload.
3. API test: compiled-review items list supports pagination/filter/search and returns envelope metadata.
4. Regression test: large bulk update no longer returns all items.

### Frontend

1. Client test: new bulk-job creator hits `/lexicon-jobs/compiled-review-bulk-update`.
2. Page test: bulk approve starts job, shows progress, polls, and refreshes counts/page.
3. Page test: items list uses paginated payload, not raw array.

### E2E

1. Admin compiled-review smoke for bulk approve:
   - start job
   - observe progress UI
   - see counts refresh on completion
2. Keep the existing export/materialize flow green after pagination changes.

## Risks

1. The current single-item decision logic may be duplicated between API and worker if not refactored into a shared service helper.
2. Pagination changes will ripple into frontend tests and any other client assuming an array response.
3. Batch counters must stay accurate under both single-item and async bulk mutations.
4. Existing branch protection and CI are already heavy; E2E additions should stay targeted.

## Non-Goals

1. Full-text search redesign for compiled review.
2. Virtualized infinite scrolling in this slice.
3. Real cancellation support for running bulk jobs.
4. Replacing Celery or the existing lexicon job queue.

## Implementation Recommendation

Execute in this order:
1. Introduce paginated item listing contract.
2. Add compiled-review bulk job API and worker.
3. Refactor shared decision logic so single-item and bulk paths use the same rules.
4. Move admin UI to job-based bulk actions and page-local item state.
5. Add backend, frontend, and E2E coverage.
6. Update project status with fresh verification evidence.
