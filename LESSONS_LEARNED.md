# Lessons Learned — Words-Codex Prototype

Hard-won lessons from building the prototype. Each section describes what went wrong, why, and what to do differently.

---

## 1. NLP: Consolidate to Backend Only

**What happened**: We had dual NLP stacks — frontend (wink-nlp, compromise, custom rule-based lemmatizer in Web Workers) and backend (spaCy, NLTK). The custom client-side lemmatizer needed repeated emergency fixes:
- `waves` → `wav` (over-truncation of `-es` suffix)
- `something` → `someth` (aggressive `-ing` truncation on non-verbs)
- Various edge cases with irregular verbs/nouns

**Why it failed**: Rule-based lemmatization is a solved problem (spaCy does it well). Reimplementing it client-side with regex rules created an endless whack-a-mole of edge cases. Having two different lemmatizers meant the same word could resolve differently on frontend vs backend.

**What to do**: All NLP goes through backend spaCy endpoints. Frontend sends raw text, backend returns lemmatized results. No client-side lemmatization at all. Accept the network round-trip cost — correctness matters more than latency here.

**Files that suffered**: `simple-lemmatizer.js`, `nlp-processor.js`, `nlpProcessor.ts` — all repeatedly patched.

---

## 2. Background Jobs: Use a Real Task Queue

**What happened**: Word list imports and lexicon enrichment used database polling — a `WordListImportJob` row with status/progress fields, polled every 1 second from the frontend. For large imports (7k+ words), the job would appear stuck at "Processing 100%" because:
1. The import completed but the follow-up `add-to-queue` step timed out
2. The modal was coupled to the async operation lifecycle
3. No proper timeout/cancellation mechanism

**Why it failed**: Database polling is fundamentally wrong for job management. No backpressure, no worker isolation, no retry semantics, no dead letter queue. The database becomes a bottleneck and the polling interval is always wrong (too fast = wasted queries, too slow = poor UX).

**What to do**: Celery + Redis (or Dramatiq, or ARQ). Proper job states, progress callbacks via WebSocket/SSE, timeout handling, dead letter queues. The frontend subscribes to progress events, never polls.

**Files that suffered**: `WordListImportJob` model, `word_lists.py` API, `CreateWordListModal.tsx`, `wordListService.ts`.

---

## 3. State Management: Don't Use sessionStorage

**What happened**: The ePub import flow spans 3 pages (`/import` → `/import/review` → `/import/success`). Import results were stored in `sessionStorage` to pass between pages. This broke on:
- Page refresh (sessionStorage survives but component state doesn't match)
- Browser back/forward navigation
- Tab duplication
- Any error that caused a re-render

**Why it failed**: sessionStorage is not a state management solution. It's a key-value store with no reactivity, no type safety, no invalidation strategy. Coupling UI state to browser storage APIs creates invisible dependencies.

**What to do**: Zustand store with persistence middleware (or React Context for simpler cases). Critical import state should also be persisted to the backend (the import job itself tracks progress), so the frontend can always recover by querying the backend.

**Files that suffered**: `importService.ts`, `review/page.tsx`, `success/SuccessPageClient.tsx`, `recoveryService.ts`.

---

## 4. Retry Logic Must Be Operation-Aware

**What happened**: The API client had generic retry logic with exponential backoff. When a large `add-to-queue` POST (7k+ word IDs) timed out at 30 seconds, the retry logic fired again, creating:
1. Concurrent duplicate POST requests
2. Race conditions on `uq_user_meaning` unique constraint
3. Cascading 500 errors from duplicate key violations
4. Frontend stuck in retry loop

**Why it failed**: Not all operations are safe to retry. GETs are idempotent — retry freely. POSTs that create resources are not. A 30-second timeout doesn't mean the request failed — the server may still be processing it.

**What to do**:
- Never retry non-idempotent POSTs automatically
- Use idempotency keys for operations that must be retryable
- Deduplicate inputs before insert (the backend now does `set(word_ids)`)
- Different timeout/retry policies per operation type (lookup: 10s/3 retries, import: 180s/0 retries)
- Distinguish timeout from failure — a timeout means "unknown", not "failed"

**Files that suffered**: `wordListService.ts`, `word_lists.py`, `CreateWordListModal.tsx`.

---

## 5. Large Imports Need Different Code Paths

**What happened**: The same import pipeline handled 50 words and 7000 words. At scale:
- Frontend NLP processing froze the UI (Web Worker helped but still slow)
- Backend word lookup took minutes for 7k words
- Cache upload payload exceeded reasonable sizes
- Modal progress bar was meaningless (jumped from 10% to 90%)
- Memory usage spiked on both client and server

**Why it failed**: O(n) operations that are fine at n=50 become painful at n=7000. The UX expectations are also different — 50 words should feel instant, 7000 words is a background job.

**What to do**:
- Threshold at ~500 words: below = synchronous, above = background job
- Chunked processing with real progress (process 100 words, report progress, continue)
- Backend-driven import for large files (upload ePub to backend, process there)
- Compact payloads before transmission (top 8 variations instead of all)
- Stream progress via WebSocket/SSE instead of polling

---

## 6. Test Database Isolation Is Non-Negotiable

**What happened**: Early in development, tests ran against the dev database and destroyed real data. A safety guard was added to `conftest.py` that refuses to reset any database not named `*_test`.

**Why it matters**: This is a one-strike lesson. Losing development data (imported books, learning progress, curated lexicon entries) costs hours of manual re-creation.

**What to do**:
- Dedicated test database with safety guards (already implemented, keep it)
- `docker-compose.test.yml` for isolated test runs
- Never use `--force` flags to bypass safety checks
- CI/CD should use ephemeral databases

---

## 7. Next.js 16 Async searchParams

**What happened**: Next.js 16 changed `searchParams` in page components to be async Promises. Code that accessed `searchParams.listId` directly broke silently.

**What to do**: Always delegate query param handling to client components. Use `useSearchParams()` hook in client components, never access `searchParams` prop directly in server components.

---

## 8. Hardcoded Admin Credentials

**What happened**: `admin.py` had `admin/admin123` hardcoded for the default admin user. This is a security vulnerability if deployed.

**What to do**: Environment-based credentials. Seed script reads from env vars. No default passwords in source code.

---

## 9. ePub.js Quirks

**What happened**: epub.js (the ePub parsing library) has several issues:
- Doesn't work in Web Workers (needs DOM access)
- Memory leaks on large files if not properly destroyed
- Inconsistent chapter ordering across ePub formats

**What to do**: Parse ePubs on the backend (Python has better ePub libraries). If client-side parsing is needed, use it only for preview/metadata, not full text extraction.

---

## 10. What Went Well

These patterns proved their worth and should be carried forward:

1. **SM-2 algorithm** — Clean 91-line implementation. Correct, well-tested, no issues.
2. **Multi-provider abstractions** — Swapping TTS/LLM/image providers was painless. The adapter pattern works.
3. **Content hash caching** — SHA-256 hash of ePub file → cache lookup. Elegant deduplication.
4. **Concept/synset model** — WordNet synsets as the unit of learning (not words) is the right abstraction.
5. **R/U/L mastery dimensions** — Recognition, Usage, Listening as separate scores per concept. Captures real learning better than a single score.
6. **Review interleaving** — Mixing card types (flashcard, cloze, listening, concept) keeps reviews engaging.
7. **Docker Compose with profiles** — `--profile tools` for pgAdmin/Redis Commander, `--profile tests` for Playwright. Clean separation.
8. **Pydantic validation** — Strong request/response schemas caught many bugs at the API boundary.
9. **Alembic migrations** — 37 migrations tracked schema evolution cleanly. No manual SQL needed.
10. **Audit logging** — Every admin action logged with user, IP, changes. Essential for multi-user admin.
