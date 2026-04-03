# Codex Prompt: Implement admin EPUB cache management by reusing the existing shared EPUB import pipeline

You are working in the repo `words-v2`.

## Non-negotiable design rule

Do **not** create a second copy of the EPUB cache model or copy EPUB metadata into new admin-only cache tables.

The admin portal must **reuse the same shared backend pipeline, cache entities, extracted-entry cache, and word-list logic that the user-side EPUB import already uses**.

The imported result for the same exact EPUB file must be identical regardless of whether it was triggered by:
- a normal user upload
- an admin single import
- an admin bulk pre-import

The admin portal is a **management and orchestration layer** over the existing shared import/cache system, not a separate implementation.

---

## Current repo reality that must drive the design

The repo already has a shared EPUB import/cache flow centered on:

- `ImportSource` as the versioned cache identity + source metadata + cache status
- `ImportSourceEntry` as the cached extracted/matched entries
- `ImportJob` as the per-trigger/per-user import session + progress/audit record
- `process_source_import` / `process_word_list_import` as the worker entrypoint
- `get_or_create_import_source`
- `create_import_job`
- `fetch_review_entries`
- `create_word_list_from_entries`

The repo also already has generic word-list storage based on `WordList` + `WordListItem(entry_type, entry_id)`, so imported lists and manually created lists are already aligned structurally.

The admin implementation must build on top of that.

---

## Primary goal

Implement an admin-side EPUB cache management feature that:

1. shows cached EPUB import sources and their metadata
2. shows the import/cache usage history per source
3. allows safe deletion / bulk deletion of cache records
4. allows admin bulk pre-import of multiple EPUB files, where each file becomes its own normal import job
5. allows monitoring of those jobs/batches even after refresh or navigating away and back
6. reuses the exact same extraction, matching, caching, review-entry, and word-list creation behavior that user-side import already uses

---

## Key principle: what to reuse vs what to add

### Must reuse as-is or by shared refactor

Use these as the shared source of truth instead of duplicating them:

- `ImportSource`
  - cache identity
  - source hash
  - title
  - author
  - publisher
  - language
  - source identifier
  - published year
  - ISBN
  - status
  - matched entry count
  - created/processed timestamps

- `ImportSourceEntry`
  - cached matched word/phrase entries
  - frequency count
  - snapshots used for review sorting/filtering

- `ImportJob`
  - who triggered the import
  - when it was created / started / completed
  - progress stage
  - counts
  - error state
  - association to `ImportSource`
  - association to created `WordList` if a list is later created

- existing shared matching/review/list-creation services

### Only add minimal new admin-specific schema where derivation is not enough

Allowed additions:

1. a minimal **batch grouping** model for admin bulk pre-import
2. minimal new job classification fields if needed for filtering/admin UX
3. soft-delete / deletion-audit fields on the shared `ImportSource` model so history remains readable after cache deletion
4. immutable display snapshot fields on `ImportJob` only where needed to make history rendering resilient
5. indexes that support admin list/history queries

Do **not** add another `CachedBook`, `AdminCachedBook`, `BookCache`, `EpubCacheMetadata`, or similar duplicate metadata table.

---

## High-level updated design

## 1. Treat `ImportSource` as the admin cache record

The admin cache table/page should be a view over `ImportSource`, not a new table.

### Admin cache list columns

The list should come from `ImportSource` plus derived fields from related `ImportJob`s.

Show:

- Title
- Author
- Publisher
- ISBN
- Published year
- Language
- Source identifier
- Status
- Matched entry count
- First imported at
- First imported by (user email / id / role)
- Processing duration
- Cache hit count
- Last reused at
- Last reused by
- Source hash (hidden by default or in details / copy action)

### How to derive the audit fields without new duplicate tables

Use existing `ImportJob` rows.

Interpretation:

- **The real processing job** for a source is the earliest related job with `started_at IS NOT NULL`
- **A cache-reuse job** is a related job that completed from cache without needing worker extraction
- Current user-side semantics already distinguish this through job timing / cache behavior

Derived fields:

- `first_imported_at`
  - earliest processing job `started_at` or `created_at`
- `first_imported_by`
  - the user on that earliest processing job
- `processing_duration_seconds`
  - processing job `completed_at - started_at`
- `cache_hit_count`
  - count of completed jobs for the same `ImportSource` that were served from cache
- `last_reused_at`
  - latest cache-hit job `created_at`
- `last_reused_by`
  - user on latest cache-hit job

### Important consequence

Because `ImportJob` already gives per-user/per-trigger history, you do **not** need a separate “cache usage audit” table for the requirements currently stated.

However, history must remain readable after cache deletion. To guarantee that, use the shared models below instead of duplicating source metadata into a second active-cache table:

- add soft-delete fields to `ImportSource`
- optionally add immutable display snapshot fields to `ImportJob` for resilient history rendering

Recommended additions:

### Shared `ImportSource` deletion fields

- `deleted_at` nullable
- `deleted_by_user_id` nullable
- `deletion_reason` nullable

Recommended behavior:

- deleting cache sets `deleted_at` and `deleted_by_user_id`
- cached `ImportSourceEntry` rows are deleted
- `ImportSource` metadata row remains for audit/history and safe joins
- exact-cache lookup for new imports must ignore rows where `deleted_at IS NOT NULL`
- if the same EPUB is uploaded again later, the shared pipeline may either
  - reactivate the same `ImportSource` row by clearing deletion fields and rebuilding entries, or
  - create a fresh active row after adjusting uniqueness semantics

Prefer **reactivating the same shared `ImportSource` row** to avoid duplicate metadata rows for the same exact source/version and to keep the admin cache model simple.

### Optional but recommended `ImportJob` snapshot fields

These are **not** a second source of truth for active cache metadata. They are immutable display snapshots only, used so history UI never breaks even if a source row is missing or later changed.

Recommended nullable fields:

- `source_title_snapshot`
- `source_author_snapshot`
- `source_isbn_snapshot`

Populate them when the job is created or first associated with an `ImportSource`.

---

## 2. Add only a minimal batch wrapper for admin bulk pre-import

Admin bulk pre-import needs a persistent grouping concept that survives refresh and lets the UI reconnect to a specific batch.

### Add a minimal `ImportBatch` model

Suggested fields:

- `id`
- `created_by_user_id` (FK to users)
- `batch_type` (for now fixed to `epub_preimport`)
- `name` nullable
- `created_at`

Do not duplicate file metadata here.

### Add nullable `import_batch_id` to `ImportJob`

This lets one batch own many normal import jobs.

### Optional but recommended: add `job_origin` to `ImportJob`

Recommended enum-like string values:

- `user_import`
- `admin_preimport`

Default to `user_import`.

Why:
- lets admin filter pre-import jobs cleanly
- avoids heuristic filtering later
- keeps one shared `ImportJob` table for all origins

This is a minimal shared extension, not a duplicate workflow.

---

## 3. Refactor shared upload/enqueue logic out of the user router private helper

The current upload helper should not stay as an internal implementation detail buried in a user router if admin routes also need it.

### Required refactor

Extract the shared “save upload -> hash -> get/create source -> create job -> maybe enqueue worker” flow into a shared service function, for example:

- `app/services/epub_import_jobs.py`
- or another clearly shared service module

Suggested function signature:

```python
async def enqueue_epub_import_upload(
    *,
    db: AsyncSession,
    actor_user: User,
    file: UploadFile,
    list_name: str | None,
    list_description: str | None,
    job_origin: str = "user_import",
    import_batch_id: uuid.UUID | None = None,
    enforce_active_import_limit: bool = True,
) -> tuple[ImportJob, ImportSource, bool]:
    ...
```

Return:
- created job
- resolved import source
- whether the job was completed immediately from cache

### User-side endpoints must be refactored to call this shared service

Use it from:
- `/api/imports`
- `/api/word-lists/import`

### Admin-side endpoints must also call this same shared service

Use it from:
- admin single pre-import
- admin bulk pre-import

No duplicated upload hashing / cache resolution / job creation logic.

---

## 4. Admin bulk pre-import must be the same import process, not a special-case parser

When admin uploads multiple EPUB files:

- each file becomes **one normal `ImportJob`**
- each job goes through the **same source hash resolution**
- each job points to the **same `ImportSource` model type**
- each uncached file uses the **same worker task**
- each cached file is completed immediately from cache using the same semantics

### Required behavior

- Bulk upload endpoint accepts multiple files
- Create an `ImportBatch`
- For each uploaded file:
  - call the shared enqueue function
  - set `job_origin="admin_preimport"`
  - attach `import_batch_id`
  - do not create a word list
- Return batch metadata plus created jobs

### Important

Do **not** create one giant worker job that processes all books in one task.

Each EPUB must remain its own import job.

---

## 5. Admin must reuse the same review-entry data path as user-side import review

The admin portal should be able to inspect the cached extracted entries for a source.

Do not add a separate admin extraction result format.

Reuse the existing review/query service:

- same `ImportSourceEntry`
- same `fetch_review_entries`
- same filters
- same sort modes
- same response item structure as much as possible

### Admin entries view requirements

For a selected cached source, admin can view entries with:

- search
- filter by `entry_type`
- filter by `phrase_kind`
- sort by:
  - `book_frequency`
  - `general_rank`
  - `alpha`
- sort order asc/desc
- pagination

This should be an admin wrapper over the same review data users already see during import review.

---

## 6. Admin delete semantics must be cache-safe, history-safe, and must not destroy user learning data

This is critical.

Deleting an EPUB cache source must **not** delete user-created word lists or word-list items. It also must **not** break the user import-history page, admin audit views, or any SQL/query path that expects an import source relationship.

### Default delete behavior

Default admin delete should be a **soft delete on the shared `ImportSource` row** plus hard deletion of cached extracted entries.

Default admin delete should:

- keep the `ImportSource` row
- set `ImportSource.deleted_at`
- set `ImportSource.deleted_by_user_id`
- optionally set `ImportSource.deletion_reason`
- set `ImportSource.status = "deleted"` or another explicit terminal cache-deleted state
- delete related `ImportSourceEntry` rows

This preserves metadata/history joins while removing the reusable cached extraction content.

### Why soft delete is the preferred shared design

This avoids the exact failure mode the user called out:

- history pages should still render after admin deletes cache
- ORM relationships / joins should not fail because the source row vanished
- queries should not need dangerous assumptions like "source must exist"
- user and admin UIs can show an explicit "cache deleted" message instead of crashing or silently returning 500s

### User-visible behavior after cache deletion

After cache deletion, a user must still be able to:

- list old import jobs in history
- open the import job detail page
- see summary metadata such as title/author/ISBN
- see that the job completed successfully in the past

But the user must **not** be able to fetch deleted cached entries as if the cache still existed.

If the user attempts to open the deleted import review entries, create a new word list from that deleted cached import, or otherwise access the removed cached extract, the backend must return an explicit business error and the UI must show a clear message such as:

> This cached import is no longer available because an administrator deleted the cached book extract. Your import history is still محفوظ/available, but to review entries again or create a new word list from this import, please re-upload the EPUB.

Use plain English in the product; do not literally use the mixed-language placeholder above.

Recommended API semantics:

- history/list/detail endpoints: still return `200` with a `cache_deleted` flag/message
- entries/review endpoint for a deleted cache: return `410 Gone` or `409 Conflict` with a stable error code such as `IMPORT_CACHE_DELETED`
- create-word-list-from-import endpoint for a deleted cache: return `410 Gone` or `409 Conflict` with the same stable error code family

### Required response shape additions

Augment import-job/source response models with fields like:

- `cache_available: bool`
- `cache_deleted: bool`
- `cache_deleted_at: datetime | null`
- `cache_deleted_by_user_id: uuid | null`
- `cache_deleted_message: str | null`

These fields should be derived from the shared `ImportSource` row.

### Optional cleanup mode

If you still need a stronger cleanup mode, only allow it for rows that are safe to detach.

#### Mode A: `cache_only` (default and preferred)
Soft delete:
- `ImportSource` metadata row retained
- `ImportSourceEntry` rows deleted

Keep:
- `ImportJob` rows
- `WordList`
- `WordListItem`

#### Mode B: `cache_only_and_delete_orphan_jobs` (optional, use sparingly)
Soft delete cache as above, and additionally hard-delete related `ImportJob` rows **only where all of the following are true**:

- `word_list_id IS NULL`
- job is admin-originated or otherwise explicitly allowed for cleanup
- product/ops requirements permit losing those history rows

Do **not** use this mode for normal user-visible import history unless explicitly required by product.

### Never do this
- Never hard-delete the shared `ImportSource` row in the normal admin cache-delete flow
- Never delete `WordList` / `WordListItem` as part of cache cleanup
- Never delete user learning data just because cache is being purged
- Never leave history endpoints assuming `import_source` is always present and active

### Query and ORM safety requirements

This must be enforced in both backend services and API handlers:

- use left joins / null-safe hydration for source details in history views
- treat `deleted_at IS NOT NULL` as "cache unavailable" rather than "missing row"
- never issue downstream review-entry queries without first validating cache availability
- convert missing/deleted cache situations into explicit domain errors, not SQL/ORM crashes

### Bulk delete
Bulk delete should support the same explicit mode, defaulting to `cache_only`.

### Re-import behavior after deletion

A later upload of the same exact EPUB must not be treated as an active cache hit if `deleted_at IS NOT NULL`.

Preferred behavior:

- the upload resolves to the same shared `ImportSource` row
- the row is reactivated (`deleted_at = NULL`, `deleted_by_user_id = NULL`, `deletion_reason = NULL`)
- extraction runs again
- new `ImportSourceEntry` rows are created
- previous `ImportJob` history remains intact

This preserves the single shared source record while allowing cache regeneration.

---

## 7. Admin UI must be consistent with current admin job-monitoring style

The current admin portal already has a pattern where:
- an active job id is persisted in `localStorage`
- the page rehydrates on mount
- it polls the backend until completion
- recent jobs are listed from the backend

Reuse that UX pattern for EPUB pre-import monitoring.

### Required admin UI sections

Build a new admin page, for example:

- `admin-frontend/src/app/lexicon/epub-cache/page.tsx`

You may split into subcomponents, but keep the route cohesive.

### Section A: cache sources table

Server-side paginated table.

Columns:
- checkbox
- title
- author
- publisher
- ISBN
- published year
- status
- matched entries
- first imported at
- first imported by
- duration
- cache hits
- last reused at
- actions

Actions:
- open details
- delete

Selection:
- select row
- unselect row
- select all visible rows
- clear selection
- bulk delete selected

### Section B: source details panel / drawer

For one selected source:
- full metadata
- source hash
- counts
- job history table
- cached entries table (reusing review-entry query)
- delete action

### Section C: admin pre-import uploader

- multi-file EPUB upload
- optional batch name
- start pre-import button
- create one job per file via shared backend path

### Section D: batch monitor / recent batches

- show active batch if present
- recent batches list from backend
- each batch expands to jobs
- refresh survives page reload and leaving/returning

### Persistence behavior

Store:
- active batch id
- optionally last viewed batch id

On mount:
- rehydrate from `localStorage`
- refetch batch from backend
- continue polling until batch terminal

### Required history/detail UX for deleted cache

If an import job references a soft-deleted cache source:

- show the history/detail row normally
- show a visible badge such as `Cache deleted`
- show an explicit explanatory banner/message
- disable or hide actions that require cached entries, such as `Review entries` or `Create word list from this import`
- offer a clear next step: `Re-upload EPUB to regenerate import cache`

### Polling behavior

Poll batch detail endpoint on an interval until:
- all jobs terminal (`completed` or `failed`)

Then:
- stop polling
- refresh recent batches list
- refresh cache sources list

---

## 8. Admin API design

Use admin-only routes protected by `get_current_admin_user`.

Suggested endpoints:

### Cache sources

```http
GET /api/admin/import-sources
```

Query params:
- `q`
- `status`
- `sort`
- `order`
- `limit`
- `offset`

Response:
```json
{
  "total": 123,
  "items": [
    {
      "id": "...",
      "source_type": "epub",
      "source_hash_sha256": "...",
      "title": "...",
      "author": "...",
      "publisher": "...",
      "language": "en",
      "source_identifier": "...",
      "published_year": 2021,
      "isbn": "...",
      "status": "completed",
      "matched_entry_count": 456,
      "created_at": "...",
      "processed_at": "...",
      "first_imported_at": "...",
      "first_imported_by_user_id": "...",
      "first_imported_by_email": "...",
      "first_imported_by_role": "user",
      "processing_duration_seconds": 3.42,
      "source_filename": "book.epub",
      "total_jobs": 8,
      "cache_hit_count": 7,
      "last_reused_at": "...",
      "last_reused_by_user_id": "...",
      "last_reused_by_email": "...",
      "last_reused_by_role": "user"
    }
  ]
}
```

```http
GET /api/admin/import-sources/{source_id}
```

Returns one summary item plus:
- optionally usage summary counts
- optionally recent jobs preview
- deletion metadata (`deleted_at`, `deleted_by`, `deletion_reason`)

```http
GET /api/admin/import-sources/{source_id}/jobs
```

Filters:
- `from_cache=true|false|all`
- `job_origin`
- `limit`
- `offset`

Each row should include:
- import job fields
- user email
- user role
- derived `from_cache`
- derived duration

```http
GET /api/admin/import-sources/{source_id}/entries
```

Reuse the same params and output semantics as the user import review entries endpoint.

```http
DELETE /api/admin/import-sources/{source_id}?delete_mode=cache_only|cache_only_and_delete_orphan_jobs
```

```http
POST /api/admin/import-sources/bulk-delete
```

Body:
```json
{
  "source_ids": ["..."],
  "delete_mode": "cache_only"
}
```

### Import batches

```http
POST /api/admin/import-batches/epub
```

`multipart/form-data`

Fields:
- `files[]`
- `batch_name` optional

Behavior:
- create batch
- create one normal import job per file
- each job uses shared enqueue path
- return batch + jobs

```http
GET /api/admin/import-batches
```

Query params:
- `limit`
- `offset`

```http
GET /api/admin/import-batches/{batch_id}
```

Return:
- batch metadata
- aggregate counts
- jobs summary

```http
GET /api/admin/import-batches/{batch_id}/jobs
```

Return paginated jobs for that batch.

---

## 9. Query implementation details for admin source list/history

Do not N+1 the admin list.

### Required query strategy

Use aggregate/subquery-based list queries.

Recommended approach:
- base query on `ImportSource`
- left join subqueries over `ImportJob`
- join `User` only for the specific derived first/last users, not for every unrelated row

### Recommended subqueries

#### First processing job per source
Use the earliest job where:
- `import_source_id = source.id`
- `started_at IS NOT NULL`

Use window function or grouped subquery.

This provides:
- first imported by
- first imported at
- filename
- duration

#### Cache hit aggregate per source
Count jobs where:
- `import_source_id = source.id`
- cache-hit semantics apply

This provides:
- cache hit count

#### Last cache-hit job per source
Find the latest cache-hit job for:
- `last_reused_at`
- `last_reused_by`

### Suggested indexes

Add indexes to support admin list/history:

- index on `import_jobs(import_source_id, created_at desc)`
- index on `import_jobs(import_source_id, started_at, created_at)`
- index on `import_jobs(import_batch_id, created_at desc)`
- index on `import_sources(status, processed_at desc)`

Optional later:
- trigram/full-text index on title/author/publisher/isbn if admin search becomes large

---

## 10. Reuse existing worker/concurrency behavior; do not create a parallel admin worker pipeline

The worker pipeline is shared.

Admin pre-import must use the same:
- `process_source_import`
- queue
- cache resolution
- advisory locking / exact-source serialization

### Concurrency requirement

If multiple user/admin jobs refer to the same exact `ImportSource`, only one real extraction/matching pass should run.

Other jobs should:
- wait safely on the same shared source state
- or complete immediately from cache once ready

Do not create a separate admin extractor.

---

## 11. Handling limits and admin overrides

The current user flow has a per-user active import limit.

Admin bulk pre-import is different operationally.

### Required change

Make the shared enqueue function configurable so that:

- user endpoints keep the current active-import limit behavior
- admin bulk pre-import can use:
  - either a different configured limit
  - or bypass the normal per-user limit

Recommended:
- add admin-specific config like `MAX_ACTIVE_ADMIN_PREIMPORTS_PER_REQUEST`
- also enforce a max number of files per batch

### Suggested safety defaults

- max files per batch: configurable, e.g. 10 or 20
- only `.epub`
- per-file size validation if the repo already has or needs one
- return per-file result rows in batch creation response

---

## 12. Suggested shared DTO/response strategy

### Reuse when possible

- reuse `ImportJobResponse` for job-level responses when appropriate
- reuse `ReviewEntriesResponse`
- reuse item hydration logic for entry display where possible

### Add new admin DTOs only for admin-specific views

Suggested:
- `AdminImportSourceSummaryResponse`
- `AdminImportSourceDetailResponse`
- `AdminImportSourceJobResponse`
- `AdminImportBatchResponse`
- `AdminImportBatchListResponse`
- `AdminBulkDeleteImportSourcesRequest`

These are response wrappers, not new persistence models for duplicated metadata.

---

## 13. Required backend refactor structure

Suggested files:

- `backend/app/services/epub_import_jobs.py`
  - shared upload/save/hash/get-source/create-job/enqueue logic

- `backend/app/services/admin_import_sources.py`
  - admin list/detail/history/delete query/service logic
  - no extraction logic here, only admin orchestration/querying

- `backend/app/models/import_batch.py`
  - minimal batch grouping model

- update:
  - `backend/app/models/import_job.py`
  - `backend/app/api/imports.py`
  - `backend/app/api/word_lists.py`
  - add `backend/app/api/admin_import_sources.py`
  - add `backend/app/api/admin_import_batches.py`

If naming differs, keep the architecture intent:
- shared import orchestration service
- thin user/admin route wrappers
- no duplicated pipeline

---

## 14. Frontend implementation details

### Admin page route

Recommended:
- `admin-frontend/src/app/lexicon/epub-cache/page.tsx`

### Expected subcomponents

Examples:
- `EpubCacheTable`
- `EpubCacheFilters`
- `EpubCacheDetailDrawer`
- `EpubPreimportUploader`
- `EpubImportBatchMonitor`
- `EpubUsageHistoryTable`

### Client libs

Add admin client modules similar to the repo’s existing admin client style:

- `admin-frontend/src/lib/admin-epub-cache-client.ts`
- `admin-frontend/src/lib/admin-epub-batches-client.ts`

### UX requirements

- loading states
- empty states
- backend error rendering
- confirmation dialog for destructive delete
- explicit warning in delete dialog:
  - cache deletion does not remove user word lists
  - optional orphan-job deletion is separate

### Batch monitor UX

For each job show:
- filename
- title if available
- status
- from-cache badge
- created at
- started at
- completed at
- duration
- matched entries
- error if failed

### Source detail history UX

History table columns:
- time
- user email
- role
- origin (`user_import` / `admin_preimport`)
- status
- from-cache
- filename
- list name
- word list created?
- duration

---

## 15. TDD plan: what to test

Follow TDD. Implement tests first or alongside each step.

## Backend unit tests

### A. shared enqueue service
Test that the shared upload/enqueue service:
- rejects non-epub files
- hashes file contents
- resolves existing `ImportSource`
- creates `ImportJob`
- returns cache-hit job immediately when source already completed
- enqueues worker when source not completed
- respects user limit when enabled
- bypasses/uses alternate policy for admin batch mode

### B. admin source query service
Test that admin source listing:
- returns `ImportSource` metadata without duplication
- derives first processing job correctly
- derives first imported by correctly
- derives duration correctly
- derives cache-hit count correctly
- derives last reused by correctly
- filters by status and query text
- sorts by supported fields

### C. admin source delete service
Test that:
- `cache_only` soft-deletes `ImportSource` (retains metadata row) and deletes `ImportSourceEntry`
- keeps `ImportJob`
- never deletes `WordList` / `WordListItem`
- `cache_only_and_delete_orphan_jobs` deletes only jobs with `word_list_id IS NULL`
- leaves jobs backing created word lists

### D. batch creation service
Test that:
- a batch is created
- one job is created per uploaded file
- all jobs use normal shared import semantics
- duplicate exact files in a batch point to the same `ImportSource` identity if hashes match
- jobs still remain separate job records

### E. admin authorization
Test that:
- non-admin users get 403 on admin endpoints
- admins are allowed

## Backend API tests

### Cache source APIs
- list cache sources
- pagination
- sorting
- filtering
- detail endpoint
- jobs history endpoint
- entries endpoint reusing review query
- single delete
- bulk delete

### Batch APIs
- create batch with multiple epub files
- list batches
- batch detail
- list jobs for batch

## Worker / integration tests

### Shared behavior tests
- user upload and admin pre-import of same exact EPUB resolve to the same `ImportSource`
- only one real extraction path runs for the same source when jobs are concurrent
- subsequent jobs complete from cache
- admin pre-import produces the same `ImportSourceEntry` rows as user upload
- user can later create a word list from a source warmed by admin pre-import

### Safe delete integration
- delete cache source
- verify cached entries are removed
- verify existing word lists remain intact
- verify later user upload reprocesses the same EPUB again because cache is gone

## Frontend component tests

### Cache list page
- renders rows
- selection state works
- select all visible rows
- clear selection
- delete confirmation modal
- bulk delete flow

### Source detail
- job history renders
- entries table filters/sorts
- metadata renders from API

### Batch monitor
- active batch id persists in `localStorage`
- page rehydrates active batch on mount
- polling continues until terminal
- recent batches refresh after completion/failure

## E2E tests

### Scenario 1: user import then admin audit
1. User uploads EPUB A
2. Import completes
3. Admin cache page shows source A with metadata, first imported by that user, and processing duration

### Scenario 2: cache reuse audit
1. User 1 imports EPUB A
2. User 2 imports exact same EPUB A
3. User 2 job completes from cache
4. Admin source detail shows a later cache-hit history row for User 2

### Scenario 3: admin bulk pre-import and refresh recovery
1. Admin uploads EPUB B and EPUB C in one batch
2. Batch page shows two jobs
3. Refresh page while jobs still running
4. Page reconnects to active batch
5. Jobs finish and cache source list updates

### Scenario 4: admin pre-import then user reuse
1. Admin pre-imports EPUB D
2. Later a user uploads exact EPUB D
3. User job completes from cache
4. Extracted entries match the pre-imported source

### Scenario 5: cache deletion safety
1. A user creates a word list from an imported source
2. Admin deletes the source cache using safe mode
3. User word list remains intact
4. Re-upload of same EPUB triggers fresh processing because the cache source is gone

### Scenario 6: authorization
1. Non-admin opens admin cache page or calls admin API
2. Access is denied

---

## 16. Acceptance criteria

The work is complete only if all of the following are true:

1. Admin cache management uses `ImportSource` as the cache source of truth
2. No duplicate metadata cache table is introduced
3. Admin single/bulk pre-import uses the same shared enqueue + worker path as user import
4. `ImportSourceEntry` is reused for admin entry inspection
5. `ImportJob` is reused as the audit history for who imported/reused a cached source
6. Admin can list, inspect, and bulk delete cached sources
7. Admin can bulk pre-import multiple EPUB files, with one normal job per file
8. Batch monitoring survives refresh / leaving and returning
9. Existing user-side import and word-list features continue to work
10. Cache deletion never deletes user-created word lists or list items
11. Tests cover unit, API, integration, frontend, and E2E paths
12. The same exact EPUB produces the same cached extracted result whether triggered by user or admin

---

## 17. Explicit do-not-do list

Do **not**:
- create duplicate admin-only cache metadata tables
- create a separate admin EPUB extraction algorithm
- create a separate admin matching pipeline
- copy `ImportSource` metadata into batch tables
- create a second word-list storage model
- delete user word lists during cache cleanup
- bypass the shared worker/import services
- implement batch import as a single monolithic worker job for all files

---

## 18. Implementation order

Recommended order:

1. Add minimal schema changes
   - `ImportBatch`
   - nullable `ImportJob.import_batch_id`
   - optional `ImportJob.job_origin`
   - indexes

2. Extract shared upload/enqueue service from current user router helper

3. Refactor existing user routes to use the shared service

4. Add admin source query/delete service

5. Add admin batch creation/list/detail service

6. Add admin API routes with admin auth

7. Add frontend page/components/clients

8. Add or update tests at each step

---

## 19. Deliverable expectation

Produce production-quality code, migrations, tests, and frontend UI for the above.

Favor:
- shared services
- thin route handlers
- safe delete semantics
- server-side pagination/filtering
- explicit typing
- minimal schema additions
- backward compatibility

The most important architectural outcome is:
**one shared EPUB import/cache system used by both users and admins, with admin-specific management layered on top rather than duplicated.**


## Additional TDD requirements for cache deletion and history safety

Add or update tests so the following behavior is locked in before implementation is considered complete.

### Backend unit/service tests

1. **Soft delete source keeps history readable**
   - create an `ImportSource`, related `ImportSourceEntry`, and related `ImportJob`
   - soft delete the source
   - assert the source row still exists with `deleted_at` set
   - assert entry rows are deleted
   - assert history/detail hydrators still return the job without crashing
   - assert response DTO sets `cache_available = false` and `cache_deleted = true`

2. **Deleted cache blocks review entries**
   - given a completed historical job whose source is soft-deleted
   - call the review-entry service / endpoint
   - assert explicit domain error or `410/409` API response with stable code like `IMPORT_CACHE_DELETED`

3. **Deleted cache blocks create-word-list-from-import**
   - same setup
   - attempt to create a word list from the deleted cached import
   - assert explicit business error, not SQL/ORM failure

4. **History snapshots still render if source metadata changes**
   - where snapshot fields are implemented, assert detail/history can render title/author/ISBN using snapshots if needed

5. **Re-upload after deletion regenerates cache**
   - soft delete the source
   - upload the same exact EPUB again
   - assert it is not treated as active cache hit
   - assert source is reactivated and entries recreated

### API tests

1. `GET /api/import-jobs` still returns deleted-cache jobs successfully
2. `GET /api/import-jobs/{id}` returns job detail with `cache_deleted` flag/message
3. `GET /api/import-jobs/{id}/entries` returns `410` or `409` with explicit cache-deleted error
4. `POST /api/import-jobs/{id}/word-lists` returns `410` or `409` with explicit cache-deleted error
5. admin source-detail endpoint returns deletion metadata after admin delete
6. admin bulk delete marks sources deleted and removes entries without hard-deleting source rows

### Frontend tests

1. user import history row renders when cache is deleted
2. user import detail page shows `Cache deleted` message and disables review/list-creation actions
3. admin cache table can show deleted rows if requested and labels them correctly
4. admin delete action updates the source row in-place rather than removing history-dependent UI data unexpectedly

### End-to-end tests

1. user imports EPUB -> admin deletes cache -> user history still loads -> user sees explicit message -> review entries action is blocked cleanly
2. user imports EPUB -> admin deletes cache -> user re-uploads same EPUB -> cache is regenerated -> review entries works again
3. admin bulk pre-imports multiple books -> delete one cache -> other batch/job/history pages remain unaffected

## Definition of done additions

The implementation is not complete unless all of the following are true:

- admin cache delete no longer causes missing-source crashes in user history or admin views
- user sees an explicit product message when cache was deleted
- deleted cache is treated as unavailable for review/list-creation, not as a generic failure
- re-uploading the same EPUB after deletion regenerates cache through the shared pipeline
- all behavior above is covered by automated tests
