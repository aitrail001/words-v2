# Codex implementation prompt: generic word lists + EPUB import review flow for `words-v2`

You are implementing a production-grade **generic word list** system and an **EPUB import -> review -> create list** workflow in the `words-v2` repo.

Work from the current codebase, not from a blank slate.

## 0) First, review the current repo and preserve what is already useful

Read these existing areas before changing anything:

- `backend/app/tasks/epub_processing.py`
- `backend/app/api/word_lists.py`
- `backend/app/api/imports.py`
- `backend/app/api/import_jobs.py`
- `backend/app/models/book.py`
- `backend/app/models/epub_import.py`
- `backend/app/models/import_job.py`
- `backend/app/models/word_list.py`
- `backend/app/models/word_list_item.py`
- `backend/app/models/word.py`
- `backend/app/models/word_form.py`
- `backend/app/models/phrase_entry.py`
- `backend/app/models/learner_catalog_entry.py`
- `backend/app/models/learner_entry_status.py`
- `backend/app/services/knowledge_map.py`
- `frontend/src/app/imports/page.tsx`
- `frontend/src/lib/imports-client.ts`
- `frontend/src/app/knowledge-list/[status]/page.tsx`
- related backend/frontend tests

## 1) Current-state findings you must take into account

The current implementation is intentionally preliminary. The new implementation must fix these issues instead of building around them blindly.

### Current problems

1. There are **two overlapping EPUB import flows**:
   - `/api/imports` with `EpubImport`
   - `/api/word-lists/import` with `ImportJob`
   They duplicate responsibility and should be unified behind one import/review pipeline.

2. The worker currently **creates new `Word` rows during EPUB processing**.  
   This is **not allowed** for the new flow. Imported entries must only come from the existing lexicon / learner catalog.

3. The current EPUB import creates a `WordList` immediately.  
   The new product requires a **review step first**, where the user can filter, sort, select, deselect, bulk select/deselect, and then create a normal generic list.

4. `WordListItem` is currently **word-only** via `word_id`.  
   This cannot support phrases/idioms. The list model must become **generic**.

5. The repo already has a better generic abstraction in `LearnerCatalogEntry` and `knowledge_map` for mixed `word` and `phrase` entries. Reuse that instead of inventing a parallel entry system.

6. The current worker stores `Book.file_path` even though the uploaded file is deleted at the end of processing.  
   The new design must **not persist file paths**, uploaded files, or raw book text.

7. The current normalization logic is too rough:
   - hard stop-word filtering
   - `len(token) > 2`
   - spaCy blank fallback that does not guarantee real lemmatization
   This is not good enough for a vocabulary product.

8. Current tests encode the old behavior (including creating words during import).  
   Those tests must be replaced with TDD tests for the new behavior.

## 2) Product goals

Implement a workflow where:

1. A user uploads an EPUB from the web client.
2. The backend worker extracts candidate vocabulary from the EPUB.
3. The backend normalizes and matches candidates against the existing lexicon / learner catalog.
4. Only entries that already exist in the DB are kept.
5. The user is shown a reviewable list of matched entries.
6. The user can filter and sort the review list by:
   - entry type (`word`, `phrase`)
   - phrase kind where available (for example idiom, phrasal verb, collocation)
   - frequency in the book
   - general frequency / browse rank
   - alphabetic order
7. The user can select / deselect / bulk select / bulk deselect entries.
8. The user creates a **normal generic word list** from the selected entries.
9. That created list behaves exactly like a manually created list:
   - rename
   - edit
   - add / remove items
   - add one-by-one
   - bulk add
   - sort
   - card / tag / list view on the frontend
10. The design must be extensible so future source types can reuse the same review/list pipeline (PDF, plain text, article, subtitle file, etc.).

## 3) Non-negotiable rules

### 3.1 Do not cache the source book or raw text
For copyright/privacy reasons:

- Do **not** persist the uploaded EPUB file after processing.
- Do **not** persist raw extracted text.
- Do **not** persist long snippets or context sentences from the source.
- Do **not** persist unmatched raw phrases/words.

What may be persisted:

- exact source hash
- descriptive metadata (title, author, identifier, language)
- processing/version metadata
- matched canonical entry references
- aggregate counts/frequencies
- optionally small, policy-safe normalization metadata, but default to **base-form-only storage**

### 3.2 Do not create lexicon entries during import
Never create new `Word`, `PhraseEntry`, `ReferenceEntry`, or learner catalog rows from imported source text.

### 3.3 The user must not see cache-hit/cache-miss details
The backend may reuse cached extraction results transparently, but the UX should look the same either way.

## 4) Final architecture to implement

## 4.1 Unify import flows into one generic import-review pipeline

Replace the split preliminary flows with a single architecture:

### A. Global cached source record
A source-level record that represents the uploaded document and the reusable extracted result.

Suggested model name:
- `ImportSource` (preferred), or a similarly generic name

Fields should include at least:

- `id`
- `source_type` (`epub` for now)
- `source_hash_sha256`  ← exact file hash, primary exact identity
- `pipeline_version`
- `lexicon_version`
- `title`
- `author`
- `language`
- `source_identifier` (EPUB package identifier / ISBN-like metadata if available)
- `status`
- `matched_entry_count`
- `created_at`
- `processed_at`

### B. Cached matched entry rows
A child table holding only canonical matched entries and aggregate counts.

Suggested model name:
- `ImportSourceEntry`

Fields should include at least:

- `id`
- `import_source_id`
- `entry_type` (`word`, `phrase`)
- `entry_id`
- `frequency_count`
- `browse_rank_snapshot` or enough information to sort stably
- optional `phrase_kind_snapshot`
- optional `cefr_level_snapshot`
- optional `normalization_method`
- no raw text content

Unique constraint:
- `(import_source_id, entry_type, entry_id)`

### C. Per-user import session / job
Keep a user-facing per-upload/session record. You may reuse and evolve `ImportJob`, but change its meaning:
- it should represent the user’s upload/review session,
- and reference the reusable cached `ImportSource`.

It should track:
- user
- source filename shown to user
- status
- progress
- chosen default list name
- linked `import_source_id`
- linked created `word_list_id` after final creation
- error fields

This allows:
- same exact EPUB processed once globally
- multiple users or repeated uploads reusing the same cached extracted entry set
- no raw-content storage

## 4.2 Exact source identity and cache policy

### Use SHA-256 of the uploaded file bytes as the primary exact identity
Do **not** use MD5.
Do **not** use title+author+ISBN as the primary exact-cache key.

Use metadata only as secondary descriptive information.

Cache key conceptually is:

`(source_type, source_hash_sha256, pipeline_version, lexicon_version)`

Reason:
- exact file hash gives exact duplicate detection
- `pipeline_version` invalidates cache when extraction/normalization changes
- `lexicon_version` invalidates cache when the lexicon/catalog changes enough that matching results would change

Practical guidance:
- make `pipeline_version` an explicit constant/version string in the import pipeline
- make `lexicon_version` an explicit version string or catalog revision marker; if the repo does not already have one, add a simple configurable/manual version first
- do not treat cache rows as timeless; versioning must be real and test-covered

### Metadata handling
For EPUB metadata, parse and store (when present):
- title
- creator/author
- language
- unique identifier / ISBN-like identifier

But do **not** rely on metadata as exact identity.

## 4.3 Replace word-only list items with generic list items

The created list must support `word` and `phrase` entries.

### Preferred migration approach
Evolve `WordListItem` to generic entry references instead of creating a second list system.

Add fields:
- `entry_type`
- `entry_id`

Keep unique constraint:
- `(word_list_id, entry_type, entry_id)`

Migration/backfill:
- existing rows with `word_id` must become `entry_type='word', entry_id=word_id`
- preserve existing user data
- after migration, application logic must use generic entry references
- remove or stop using `word_id` once migration is complete and code is switched over

### Why
This keeps one list system, so imported lists and manual lists are the same product object.

## 4.4 Reuse `LearnerCatalogEntry` and knowledge-map services

Do not build a second parallel search/index layer for generic entries.

Use existing repo abstractions where possible:

- `LearnerCatalogEntry` for mixed entry summaries and browse rank
- `knowledge_map` services for:
  - entry lookup
  - summary hydration
  - search behavior
  - sorting patterns
  - generic word/phrase handling

The new list APIs should be able to hydrate list items into display objects consistent with the knowledge map UI.

## 5) Extraction and matching design

Implement a deterministic pipeline with clear precedence rules.

## 5.1 EPUB text extraction
For EPUB:
- parse the book safely
- extract text from relevant document/spine content
- skip obvious non-reader boilerplate where reasonable (for example nav/toc documents) if this is easy and reliable
- do not persist the extracted text after processing

Create the code so future source types can plug into the same pipeline through a small extractor interface, e.g.:

- `SourceTextExtractor`
- `EpubTextExtractor`

## 5.2 Words: normalization and matching rules

### Required precedence for single-word matching
For each candidate surface form, resolve in this order:

1. **Exact existing entry wins**
   - if the exact normalized surface form already exists in the lexicon as a standalone word entry, keep that exact entry
   - example: if `ran` exists as its own entry with its own meaning, use `ran`

2. **Word-form mapping next**
   - if exact entry does not exist, check `WordForm.value`
   - if there is a unique base-word mapping, use that base word
   - example: `apples -> apple`, `ran -> run`

3. **Lemmatizer fallback**
   - only after exact-entry and `WordForm` lookup
   - use explicit, deterministic lemmatization
   - do not rely on a blank spaCy pipeline magically providing good lemmas

4. **Ambiguous cases**
   - if a surface form maps to multiple possible base entries and cannot be resolved deterministically, do not silently invent a result
   - either disambiguate using available POS/context in a deterministic way, or skip the ambiguous token
   - keep count statistics, but do not persist unmatched raw text

### Important filtering rule
Do **not** drop valid entries just because:
- spaCy marks them as stop words
- they are 1–2 characters long

Instead:
- keep entries if they resolve to a real lexicon entry
- use DB existence as the primary filter, not generic stop-word heuristics

## 5.3 Phrases / idioms: extraction strategy

### V1 strategy
Use a **lexicon-driven exact matching** strategy for phrases instead of open-ended phrase mining.

Reason:
- the product only keeps entries that already exist in the DB
- phrase matching is more reliable if driven by existing `PhraseEntry` / learner catalog data
- this is much better than extracting arbitrary n-grams and hoping they exist

### Implementation guidance
Build a phrase matcher from phrase entries in the learner catalog:
- use `LearnerCatalogEntry` rows where `entry_type='phrase'`
- build patterns from `display_text` and/or `normalized_form`
- match case-insensitively
- normalize whitespace, apostrophes, and hyphen variants carefully
- prefer exact and deterministic rules over aggressive stemming

### Overlap resolution
When phrase matches overlap, use deterministic precedence:
1. longer span first
2. then higher-confidence canonical exactness
3. then better browse rank / lower rank number
4. then stable tie-breaker

### Word vs phrase counting
Count words and phrases independently.
A matched phrase does **not** suppress its component words.

## 5.4 General normalization rules

At minimum implement:
- Unicode normalization (NFKC or similarly appropriate)
- lowercase canonical matching key
- apostrophe normalization (`'`, `’`)
- hyphen/dash normalization where safe
- whitespace collapsing
- punctuation trimming around tokens
- deterministic normalization versioning

Do not over-normalize phrases into something semantically different.

## 5.5 General frequency sorting
For mixed entry sorting, use a generic cross-entry ranking source.
Prefer:
- `LearnerCatalogEntry.browse_rank`

Use nulls/unranked-last behavior consistently.

## 6) API design requirements

You may reuse and reshape current endpoints, but end state must support the following behavior cleanly.

## 6.1 Import/review endpoints

### Upload/import
A user uploads an EPUB and receives a session/job response.

Suggested route:
- `POST /api/source-imports`
or keep compatibility with:
- `POST /api/word-lists/import`

Behavior:
- accept EPUB upload
- save to temporary storage only
- hash with SHA-256 while streaming
- create/reuse `ImportSource`
- create/update user `ImportJob` / review session
- enqueue worker if needed
- on cache hit, complete quickly and transparently
- frontend should not need to know whether it was cached

### Get import status
Suggested route:
- `GET /api/source-imports/{session_id}`
or keep `GET /api/import-jobs/{job_id}`

Return:
- status
- progress
- source metadata
- summary counts
- created list id if already created
- no raw text

### List reviewable matched entries
Add an endpoint like:
- `GET /api/source-imports/{session_id}/entries`

Query params:
- `q`
- `entry_type`
- `phrase_kind`
- `sort` (`book_frequency`, `general_rank`, `alpha`)
- `order`
- `limit`
- `offset`

Return each row with at least:
- `entry_type`
- `entry_id`
- `display_text`
- `normalized_form`
- `phrase_kind`
- `frequency_count`
- `browse_rank`
- `cefr_level`
- any safe summary fields useful for UI

### Create list from selected entries
Add endpoint like:
- `POST /api/source-imports/{session_id}/word-lists`

Request:
- `name`
- `description` optional
- `selected_entries: [{entry_type, entry_id}]`

Behavior:
- validate selected entries belong to the import session/source
- create a normal `WordList`
- create generic `WordListItem` rows
- set `frequency_count` from import-source entry count
- upsert safely if needed
- return the created list

## 6.2 Manual generic word-list CRUD endpoints

Implement or complete support for:

### Create empty list
- `POST /api/word-lists`

### Rename/update list
- `PATCH /api/word-lists/{id}`

### Get list
- `GET /api/word-lists/{id}`

### List lists
- `GET /api/word-lists`

### Delete list
- existing delete endpoint is fine, adapt as needed

### Add one entry
- `POST /api/word-lists/{id}/items`
Request must use generic entry references:
- `entry_type`
- `entry_id`

Do not allow blind add by raw text here.
Raw-text add must resolve through the lexicon first.

### Remove one entry
- `DELETE /api/word-lists/{id}/items/{item_id}`

### Bulk add preview / resolve
Add an endpoint like:
- `POST /api/word-lists/resolve-entries`
or
- `POST /api/word-lists/{id}/bulk-resolve`

Input:
- raw text pasted by user

Behavior:
- parse terms
- normalize
- resolve only existing lexicon entries
- return:
  - found entries
  - ambiguous entries
  - not found count
- do not persist unmatched raw content

### Bulk add apply
Add endpoint like:
- `POST /api/word-lists/{id}/bulk-add`

Input:
- resolved selected entries from the preview stage

Behavior:
- add/upsert generic items
- aggregate duplicates before insert
- merge counts deterministically

## 6.3 Search for manual add
For manual one-by-one add, reuse or extend the generic knowledge-map search, not the word-only search, so phrases can be added too.

## 7) Bulk input parsing rules

The user asked for space-separated or newline-separated bulk add, but phrases contain spaces, so naive splitting is ambiguous.

Implement this safely:

### Preferred parsing behavior
- newline, comma, and semicolon are primary separators for mixed words/phrases
- quoted phrases are supported in whitespace-heavy input
- plain whitespace-only mode can still be used for single words

Examples:
- `run\nmake up for\non the other hand`
- `run, "make up for", "on the other hand"`
- `run walk swim`  ← single-word whitespace mode

Return a preview so the user can verify what will be added.

## 8) Frontend requirements

## 8.1 Import page
Replace the current very preliminary imports page with a real flow:

1. Upload EPUB
2. Show processing state
3. Navigate to or render review UI when ready

## 8.2 Review page behavior
The review UI must support:

- table/list of matched entries
- search
- filter by type
- filter by phrase kind where available
- sort by:
  - in-book frequency
  - general rank
  - alphabetic
- checkbox selection
- select all filtered
- deselect all filtered
- selected count
- create-list action with name/description
- good empty/error/loading states

The user should not see “cache hit” vs “cache miss”.

## 8.3 Word list page behavior
Generic word lists should support:
- rename
- delete
- remove items
- add one item
- bulk add
- search within list
- sort like knowledge list where appropriate
- multiple view modes:
  - card
  - tag
  - list

Reuse existing knowledge-list UI patterns where possible.

## 9) Backward compatibility / migration

## 9.1 Existing data migration
Provide a migration for existing `WordListItem` rows:
- convert current word-only rows into generic item references
- preserve all existing lists

## 9.2 Existing endpoints
If feasible, preserve compatibility for:
- `POST /api/word-lists/import`
- `GET /api/import-jobs/{id}`

But change their behavior to fit the new review-first workflow.

At minimum, do not leave two unrelated EPUB pipelines alive.

## 10) Testing strategy: strict TDD

Write failing tests first, then implement.

## 10.1 Unit tests
Add unit tests for:

### Source identity / cache
- exact SHA-256 hashing
- same file hash => same exact source key
- changed `pipeline_version` invalidates cache
- changed `lexicon_version` invalidates cache

### Word normalization
- exact surface form wins over base-form normalization
- `apples -> apple`
- `ran -> run` when no exact `ran` entry exists
- `ran` exact entry wins if present
- ambiguous form handling is deterministic

### Phrase matching
- exact phrase match from learner catalog
- case-insensitive matching
- apostrophe/hyphen normalization
- overlap resolution prefers longer match

### Privacy/copyright behavior
- no raw text persisted
- temp upload file deleted
- unmatched raw tokens/phrases not persisted

## 10.2 Service / DB tests
Add tests for:

- import cache hit reuses `ImportSourceEntry` rows and does not reprocess text
- import cache miss processes and stores canonical entry refs only
- concurrent same-source creation results in one canonical `ImportSource` row
- concurrent same-source worker attempts do not duplicate cached entry rows
- worker retry / duplicate delivery is idempotent and does not create duplicate list items
- exact-source lock/upsert path behaves correctly under contention
- creating a word list from selected import entries creates standard generic list items
- manual add by generic entry reference works
- bulk resolve returns found/ambiguous/not-found preview
- bulk add persists only valid selected entries
- generic list hydration works for both word and phrase items

## 10.3 API tests
Add tests for:

- upload EPUB -> job/session created
- duplicate exact upload -> transparent reuse
- duplicate concurrent upload does not create duplicate canonical source work
- invalid EPUB -> failed state
- review entries endpoint filtering/sorting/pagination
- create list from selected import entries
- create empty list
- rename list
- add one entry
- remove entry
- bulk resolve
- bulk add
- permissions / ownership checks
- per-user active import limit / backpressure behavior if configured

## 10.4 Frontend tests
Add component tests for:

- upload form
- progress state
- review page filtering/sorting/selection
- select all filtered / deselect all filtered
- create list action
- list page rename/add/remove
- bulk add preview

## 10.5 E2E tests
Add at least one happy-path end-to-end flow:

1. upload EPUB
2. wait for processing
3. review entries
4. filter and select subset
5. create list
6. open list
7. rename list
8. add extra manual item
9. remove one item

## 11) Implementation details to respect

### 11.1 Prefer new service modules over bloating API/task files
Create dedicated services such as:
- import source service
- extractor service
- entry matching service
- word-list service

### 11.2 Keep worker logic deterministic
No LLM extraction.
No probabilistic “guessing” of phrases for V1.
No generation of new lexicon content.

### 11.3 Observability
Add useful structured logging and counts, but never log raw extracted source text.

### 11.4 Performance and memory
- batch DB lookups
- avoid N+1 queries
- cache phrase-matcher inputs in worker process where helpful
- paginate review results
- process EPUB content incrementally by document/spine item; do not rely on one giant concatenated string for the production path
- keep peak memory bounded by batch size + counters, not by full book size
- preload NLP / matcher resources once per worker process where practical; do not repeatedly load heavy models for every task invocation
- bulk insert/upsert matched entry rows instead of row-by-row inserts where practical

### 11.5 Scalability, concurrency, and async behavior
- Heavy extraction and matching must never run in the FastAPI request/response cycle.
- The request path may validate the file, compute SHA-256, persist a short-lived temp object reference, create/attach a job/session record, enqueue the worker, and return immediately.
- The system must support high parallel usage by queueing work safely; do not assume all jobs run at once.
- Route document-import tasks to a dedicated Celery queue such as `imports` so EPUB processing cannot starve other background jobs.
- Use dedicated worker replicas/pools for import queues rather than sharing one general-purpose pool with latency-sensitive tasks.
- Make import tasks idempotent. A worker retry or duplicate delivery must not create duplicate `ImportSource`, `ImportSourceEntry`, or `WordListItem` rows.
- Enforce DB uniqueness for canonical cached rows and list items.
- For exact-source contention, use one of these patterns:
  - `INSERT ... ON CONFLICT DO NOTHING` + reread the canonical row, or
  - a transaction-level PostgreSQL advisory lock keyed by exact source identity.
  Prefer unique constraints + upsert as the baseline; advisory locks are acceptable for serializing the expensive source-build section.
- If two users upload the same exact source while processing is already underway, the second request must attach to existing canonical work instead of launching a second full extraction.
- Keep worker time limits, but also make failures resumable/retriable without duplicates.
- Configure Celery for long-running jobs only after idempotency is real:
  - consider `task_acks_late = True`
  - set `worker_prefetch_multiplier = 1`
  - consider `worker_disable_prefetch` when using Redis if queue fairness becomes a problem
- Add rate limits / per-user active import limits so one user cannot flood the import workers.
- For multi-instance deployment, do not rely on container-local disk semantics. Use shared ephemeral storage or object storage with strict TTL deletion for the temporary source file handoff to workers.
- Add observability for queue depth, queue wait time, processing duration, worker memory/CPU, cache-hit rate, duplicate-suppressed count, and retry count.

## 12) Reasoning behind this design

This section is important: follow it.

1. **Exact-file SHA-256 is the right exact-cache key**  
   The requirement is “same exact book processed once”. Exact file bytes are the cleanest exact identity. Metadata is secondary and unreliable for exact dedupe.

2. **Metadata should still be stored, but only as metadata**  
   EPUB identifiers/titles/authors are useful for display and diagnostics, but they are not a safe primary exact-cache identity.

3. **The current word-only list model must become generic**  
   The repo already supports mixed learner entries (`word` and `phrase`) elsewhere. Word lists should align with that architecture.

4. **Do not create lexicon rows from imports**  
   The product rule is clear: if it is not already in the word/phrase DB, it should not survive import. Therefore import is a matching/resolution problem, not a lexicon-generation problem.

5. **Phrase extraction should be lexicon-driven in V1**  
   Because the app only keeps existing DB entries, exact matching against known phrase entries is safer and simpler than open-ended phrase mining.

6. **The user needs a review step**  
   Immediate list creation is too rigid. Review-before-create is the correct UX and also supports future source types.

7. **Imported lists and manual lists must be the same object**  
   This avoids a fragmented product model and keeps the long-term UX much simpler.

8. **Tests must move from “task completes” to behavior that matters**  
   Especially:
   - no raw-text persistence
   - no lexicon row creation
   - exact dedupe
   - correct normalization precedence
   - generic list support

## 13) Acceptance criteria

The implementation is done only when all of the following are true:

- uploading an EPUB no longer creates new `Word` rows
- no raw EPUB content or file path is persisted after processing
- same exact EPUB reuses cached extracted canonical entry data
- cache invalidates when pipeline or lexicon version changes
- heavy extraction/matching runs in workers, not inside the request cycle
- duplicate concurrent uploads of the same exact source do not create duplicate canonical source work
- worker retry / duplicate delivery is idempotent and does not duplicate cached rows or list items
- import work is isolated to dedicated queue(s) / worker pool(s)
- review UI appears before list creation
- review entries support filtering, sorting, and selection
- only lexicon-existing entries appear
- created list is a normal generic list, not a special import-only artifact
- generic lists support words and phrases
- manual add and bulk add both validate against the lexicon first
- tests cover unit, service/API, concurrency/idempotency, and at least one E2E flow
- the architecture is clearly reusable for future source types

## 14) Out of scope for this implementation

Do not do these in this task unless they are tiny incidental refactors:

- OCR
- PDF import implementation
- LLM-based phrase discovery
- semantic/fuzzy phrase matching
- creation of new lexicon entries from imported text
- storing context snippets from the source book

## 15) Deliverables

When you finish coding, include:

1. migrations
2. backend implementation
3. frontend implementation
4. tests
5. a short implementation note explaining:
   - main schema changes
   - cache key logic
   - normalization precedence
   - how the frontend review flow works
