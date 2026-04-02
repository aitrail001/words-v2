# 2026-04-02 Admin Large-Data Optimization Plan

## Objective

Make the admin portal usable and safe for very large lexicon datasets without loading full artifacts or large result sets into the browser, while preserving exact counts and keeping backend load bounded.

Target pages:

- `/lexicon/voice-runs`
- `/lexicon/ops`
- `/lexicon/jsonl-review`
- `/lexicon/db-inspector`

## Current Problems

### Voice Runs

- The detail route scans very large JSONL artifacts on demand.
- A hotfix already removed the worst full-file parsing path, but large runs still take around 10 seconds to load.
- The list route still builds summaries by walking run directories and deriving counts synchronously.

### Lexicon Ops

- The frontend loads all snapshot summaries and filters/paginates client-side.
- Snapshot detail performs recursive artifact discovery and per-artifact stats on demand.
- This is manageable for small snapshot counts but does not scale cleanly.

### JSONL Review

- The backend `load` route returns the entire review session including every item payload.
- The frontend filters, sorts, and paginates that full in-memory list.
- Per-item and bulk updates reload the entire session.
- This is the largest browser-memory and backend-read amplification problem.

### DB Inspector

- The list route is already server-paginated.
- Detail routes are separate, which is the right shape.
- Remaining risk is query cost, especially for `family=all`, unindexed search, and detail hydration breadth.

## Design Constraints

- Counts shown in the UI must be exact.
- Large pages must be summary-first.
- Pagination, search, and sort must be server-side.
- Full raw data should be downloaded explicitly, not hydrated into the browser.
- Avoid repeated large-file scans for the same page view when possible.
- Do not overload the backend with unbounded file parsing or large payload serialization.

## Target UX

### Voice Runs

- List page shows run summaries only.
- Detail page shows:
  - exact summary counts
  - exact per-dimension counts
  - tiny recent samples
  - artifact download links
- No route should parse the full manifest into memory.

### Lexicon Ops

- Snapshot list becomes server-filtered and server-paginated.
- Snapshot detail returns only bounded artifact metadata:
  - exact row counts
  - sizes
  - mtimes
  - workflow metadata
- Artifact browsing stays in downstream tools.

### JSONL Review

- Replace full-session hydration with:
  - session summary endpoint
  - paginated item browse endpoint
  - per-item update endpoint returning only the updated row plus summary deltas
  - bulk update endpoint returning summary only
- Filters and sort move fully server-side.
- Only the current page of items is held in browser memory.

### DB Inspector

- Keep server pagination.
- Tighten query shapes to avoid cross-family waste where possible.
- Keep detail routes separate and lazy.
- Preserve exact total counts.

## API Direction

### Voice Runs

- Keep `/voice-runs` for summary list.
- Keep `/voice-runs/{run_name}` for bounded detail.
- Internally:
  - stream JSONL once per metric family
  - avoid repeated per-request rescans when a single pass can serve multiple exact counts
  - use tail sampling for latest rows

### Lexicon Ops

- Change `/snapshots` to accept server-side query params:
  - `q`
  - `limit`
  - `offset`
- Return:
  - `items`
  - `total`
  - `has_more`
- Keep `/snapshots/{snapshot}` for detail, but ensure artifact metadata is bounded and derived with streaming helpers.

### JSONL Review

- Deprecate full `load` semantics for UI use.
- Add:
  - `GET /lexicon-jsonl-reviews/session`
  - `GET /lexicon-jsonl-reviews/items`
  - `GET /lexicon-jsonl-reviews/items/{entry_id}`
- Response split:
  - session summary with exact counts
  - paginated items with exact filtered total
- Mutations:
  - update item returns updated item plus refreshed exact counts
  - bulk update returns refreshed exact counts, not full item list
- Downloads and materialization remain explicit endpoints.

### DB Inspector

- Keep current list/detail contract.
- Improve backend implementation rather than inventing a new surface unless profiling shows a real need.

## Implementation Phases

### Phase 1: Stop Full Hydration

1. Preserve and keep the voice-run detail hotfix.
2. Redesign JSONL review backend to support server-side session summary plus item pagination.
3. Update JSONL review frontend to page/search/sort via backend instead of `session.items`.

### Phase 2: Tighten Heavy Summaries

1. Add server-side filtering/pagination to lexicon ops snapshot list.
2. Reduce snapshot detail artifact scanning overhead with shared streaming helpers.
3. Further optimize voice-run list/detail counting paths.

### Phase 3: Query Hardening

1. Review DB inspector query plans and simplify the worst shapes.
2. Keep exact counts while reducing avoidable work for `family=all`.
3. Ensure detail routes only hydrate what the UI actually renders.

## Verification Plan

### Backend

- Extend API tests for:
  - paginated JSONL review browsing
  - exact filtered counts
  - update/bulk-update summary refresh
  - paginated snapshot list
  - large voice-run detail regression

### Frontend

- Update page tests for:
  - JSONL review server-driven pagination
  - JSONL review search/filter behavior
  - snapshot list pagination/filter behavior
  - voice-run bounded detail behavior

### Performance

- Measure these endpoints on the dev stack before and after:
  - `/api/lexicon-ops/voice-runs`
  - `/api/lexicon-ops/voice-runs/{run}`
  - `/api/lexicon-ops/snapshots`
  - `/api/lexicon-jsonl-reviews/session`
  - `/api/lexicon-jsonl-reviews/items`
  - `/api/lexicon-inspector/entries`
- Capture response time and confirm no route loads entire large artifacts into process memory unnecessarily.

## Non-Goals

- Approximate counts
- Browser-side full raw artifact browsing
- Replacing download flows for raw JSONL artifacts
- Deep caching infrastructure beyond what is necessary for bounded exact-count behavior in this slice
