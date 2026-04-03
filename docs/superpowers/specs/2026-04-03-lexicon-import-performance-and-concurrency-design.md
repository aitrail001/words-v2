# Lexicon Import Performance and Concurrency Design

## Goal

Harden lexicon enrichment and voice DB imports so they can handle very large JSONL inputs (including 1,000,000+ rows) without exhausting memory, overloading DB write paths, or collapsing admin UX into a single-job view.

## Scope

In scope:
- Backend job enqueue and worker execution for:
  - `import_db`
  - `voice_import_db`
- Import pipeline performance improvements (streaming + progress persistence throttling)
- Active-job concurrency guard by `source_reference`
- Admin frontend progress UX for multiple simultaneous imports
- Time metrics for in-progress and recent jobs
- SSR hydration stability on import pages

Out of scope:
- Changing lexicon artifact schema contracts
- Changing voice generation pipeline contract
- Cross-product queue orchestration beyond lexicon job families

## Constraints

1. Only one active import job for the same `source_reference` is allowed per job family.
2. Parallel imports are allowed only when `source_reference` differs.
3. Conflict/error mode differences do not bypass the lock.
4. Once prior job for same `source_reference` is completed/failed, next import may start.

## Current Root Causes

1. API enqueue path hydrates full JSONL payload to compute row summary.
2. Import runtime hydrates full input JSONL into memory before processing.
3. Worker progress writes call `db.commit()` on each callback update.
4. Active-job state in frontend is singleton (`localStorage` key + single `job` state).
5. `import-db` page computes URL-derived context during render, creating SSR/CSR mismatch risk.

## Proposed Backend Design

### 1) Enqueue-time lightweight summary (streaming)

Replace full-row load at enqueue with streaming summary helpers:
- `summarize_compiled_rows_from_path(path)`
- `summarize_voice_manifest_rows_from_path(path)`

These should:
- Scan line-by-line
- Compute counters only
- Not materialize full rows in memory

### 2) Runtime streaming import mode

For both importers:
- Avoid `list(...)` materialization of all rows before preflight/import
- Process by bounded batches/groups from iterators
- Preserve current behavior semantics (validation, dry-run, error modes)

### 3) Throttled progress persistence

In worker tasks:
- Decouple progress callback frequency from DB commit frequency
- Commit progress when one of conditions is met:
  - `N` new rows processed (configurable default)
  - `T` ms elapsed since last commit
  - phase transition/completion/failure

Result:
- Lower DB pressure
- Less lock churn
- Better chance to stay within soft time limits

### 4) Concurrency guard by `source_reference`

At job creation for `import_db` and `voice_import_db`:
- Resolve normalized `source_reference` key from request (required for queued import path)
- Query active jobs (`queued`, `running`) for same `job_type` + same normalized source reference
- If found, return `409` with clear message:
  - `An active <job_type> job already exists for source_reference '<value>'. Wait until it finishes.`

Implementation notes:
- Keep existing target-key dedupe as secondary protection.
- Primary lock semantic is now `source_reference`.

### 5) Phase timing metrics in job payload

Track and expose:
- `queue_wait_ms` (`started_at - created_at`)
- `elapsed_ms` (running: `now - started_at`; terminal: `completed_at - started_at`)
- `validation_elapsed_ms`
- `import_elapsed_ms`

Storage approach:
- Keep in `request_payload.progress_timing` for backward-compatible schema evolution.
- Update on phase transitions and terminal states.

## Proposed Frontend Design

### 1) Multi-active-job progress panel

For both pages:
- Replace single active job UI with list of active jobs (`queued` + `running`) from `listLexiconJobs`.
- Each card shows:
  - status
  - source reference
  - input path
  - phase counters
  - timing metrics

### 2) Local persistence model

Replace singleton localStorage key with JSON array/set of tracked job IDs:
- `lexicon-import-db-active-jobs`
- `lexicon-voice-import-active-jobs`

On refresh:
- Rehydrate tracked IDs
- Reconcile with server list
- Remove terminal IDs

### 3) Hydration-safe query handling

Do not call `window.location` during render-time computed values.
Use state populated in `useEffect` only, then derive UI from state.

### 4) Recent jobs timing display

Show in recent cards:
- total elapsed
- validation elapsed
- import elapsed
- queue wait

## Error Handling and UX

- `409` lock conflict should render explicit banner/toast with source reference and job id (if available).
- Active-job cards should include “already running” context rather than implying create failure.
- Polling should be bounded and deduplicated per job id.

## Testing Strategy

Backend:
- API tests:
  - returns `409` for active same-source job
  - allows same-source after completion
  - allows different source references in parallel
- Worker tests:
  - progress commits are throttled (not per-row)
  - timing fields are populated for validating/importing/completed/failed
- Importer tests:
  - streaming summary works without full list hydration
  - large-row iterator behavior remains correct

Frontend:
- page tests for both import pages:
  - renders multiple active jobs
  - shows timing metrics
  - hydration-safe context rendering
  - lock conflict message path

## Rollout

1. Backend guard + progress/timing fields
2. Backend streaming summary/import improvements
3. Frontend multi-job/timing/hydration updates
4. Targeted regression tests

## Risks

1. Existing clients may assume optional `source_reference`; requiring lock key needs migration handling.
2. Timing fields in payload must tolerate missing values for old jobs.
3. Throttled progress updates reduce update granularity; ensure UX still appears responsive.

## Acceptance Criteria

1. Starting second import with same `source_reference` while first is active returns `409`.
2. Starting parallel imports with different `source_reference` succeeds.
3. Worker progress commits are throttled and no longer per callback.
4. Import pages display multiple active jobs concurrently.
5. No hydration mismatch on import pages under SSR.
6. In-progress and recent job cards show total/validation/import elapsed times.
