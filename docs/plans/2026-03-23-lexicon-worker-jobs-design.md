# 2026-03-23 Lexicon Worker Jobs Design

## Goal

Move the heavy lexicon admin operations onto the existing Celery worker path while keeping the backend as the control plane. The first worker-backed lexicon operations are:

- `import-db`
- JSONL Review `materialize`
- Compiled Review `materialize`

Single-entry review actions, review browsing, and DB Inspector stay in the backend.

## Why

The current bounded backend-managed lexicon import job solved page-navigation loss, but it is still process-local. A backend restart will kill the job. The current synchronous materialize paths are also the wrong execution model for file-writing operations that can fail, take time, and benefit from durable status/progress.

The repository already has an operational worker stack:

- Celery worker
- Redis broker/backend
- DB-backed status models for EPUB/word-list imports

But that existing `ImportJob` model is EPUB-specific and should not be stretched to cover lexicon artifact jobs.

## Recommended Architecture

### Backend responsibilities

- validate request inputs
- resolve allowed paths / batch ownership
- compute a stable `target_key`
- create or reuse a lexicon job record
- enqueue Celery task
- serve job status to admin pages

### Worker responsibilities

- execute long-running lexicon operations
- update job progress and current label
- persist terminal success/failure state
- write reviewed outputs / DB import effects

### UI responsibilities

- start a job
- poll status
- reconnect to an existing active job
- render terminal outputs/results

## Job Model

Add a dedicated `LexiconJob` DB model instead of reusing `ImportJob`.

Suggested fields:

- `id`
- `created_by`
- `job_type`
  - `import_db`
  - `jsonl_materialize`
  - `compiled_materialize`
- `status`
  - `queued`
  - `running`
  - `completed`
  - `failed`
- `target_key`
- `request_payload`
- `result_payload`
- `progress_total`
- `progress_completed`
- `progress_current_label`
- `error_message`
- `created_at`
- `started_at`
- `completed_at`

Why separate model:

- `ImportJob` currently encodes EPUB/word-list concepts (`book_id`, `word_list_id`, `list_name`, `source_hash`)
- lexicon jobs are artifact/batch/DB-import oriented
- separate semantics will keep status endpoints and operators clearer

## API Shape

### New endpoints

- `POST /api/lexicon-jobs/import-db`
- `POST /api/lexicon-jobs/jsonl-materialize`
- `POST /api/lexicon-jobs/compiled-materialize`
- `GET /api/lexicon-jobs/{job_id}`

### Response shape

- job identity
- type
- status
- progress counts
- current label
- result payload
- error message
- timestamps

The existing pages should switch from calling synchronous execution endpoints to calling job-creation endpoints, then polling `GET /api/lexicon-jobs/{job_id}`.

## Target Locking

Only one active lexicon job should exist for a target at a time.

Examples:

- `import_db:/app/data/lexicon/snapshots/foo/reviewed/approved.jsonl`
- `jsonl_materialize:/app/data/lexicon/snapshots/foo/reviewed`
- `compiled_materialize:batch:<batch-id>:output:/app/data/lexicon/snapshots/foo/reviewed`

Behavior:

- if an active job already exists for the same `target_key`, return that job instead of creating a duplicate
- this matches the pattern already used by EPUB imports

## Filesystem Rules

- worker must have writable access to `/app/data` in environments where lexicon writes are expected
- long-running reviewed-output writes should be worker-owned
- use temp-write then atomic rename where practical
- continue to enforce allowed-root path resolution on the backend before job creation

## Scope Boundaries

### In scope

- add `LexiconJob` model + migration
- Celery tasks for the three lexicon job types
- backend job create/status endpoints
- switch the three admin flows to backend-controlled worker execution
- progress polling + reconnect behavior

### Out of scope

- moving single-item review decisions to worker
- redesigning admin UI layout again
- moving DB Inspector to worker
- building full cancel/retry UX in the same slice

## Testing

### Backend

- model/migration tests for `LexiconJob`
- API tests for create/status endpoints
- active-job dedupe tests by `target_key`
- task tests for:
  - import-db
  - JSONL materialize
  - compiled materialize

### Frontend

- client tests for new job endpoints
- page tests for job start, polling, terminal state, reconnect

### E2E

- `Import DB` reconnect smoke
- JSONL materialize smoke via worker path
- Compiled materialize smoke via worker path

## Rollout Order

1. Add `LexiconJob` model and migration.
2. Add Celery task + backend API for `import-db`.
3. Move Import DB page to the new job API.
4. Add JSONL materialize task + API.
5. Add Compiled materialize task + API.
6. Run backend tests, frontend tests, lint, build, and targeted Playwright smoke.

## Risks

- widening the worker role without a clean lexicon job model will create mixed semantics and future cleanup cost
- writable shared `/app/data` mounts must be consistent across backend/worker environments
- target locking must be correct or reviewed outputs can be corrupted by concurrent jobs

## Recommendation

Proceed with a dedicated lexicon job framework on top of the existing Celery stack. Do not reuse the EPUB-specific `ImportJob` table, and do not migrate interactive review CRUD to the worker.
