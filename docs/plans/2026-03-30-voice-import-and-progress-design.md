# Voice Import and Progress Design

## Goal

Make lexicon import and voice import progress visible and phase-aware, make voice policy editing less confusing, expose explicit voice paths in DB Inspector, add operator-facing voice import in admin from recent voice runs, and align voice import history/error handling with DB import.

## Decisions

### 1. Import progress becomes phase-aware

`import_db` jobs will expose a clearer operator model:
- `to_validate`
- `validated`
- `to_import`
- `imported`
- `skipped`
- `failed`
- `total`

The backend will keep `progress_current_label` as the human-readable status line, but job payloads/results will add additive counters so the UI can render validation and import phases without guessing from one generic progress number.

Dry run and import both continue to use the same preflight engine. Import remains blocked by preflight failures before SQL writes.

### 2. Voice import mirrors DB import

Voice import will use the same operator shape as DB import:
- `Dry Run`
- `Import`
- `conflict_mode = fail | skip | upsert`
- `error_mode = fail_fast | continue`
- current progress
- recent jobs
- compact result details

This is an admin/operator symmetry decision only. The backend execution engines remain separate:
- `import_db`
- `voice_import_db`

The queue/job model stays shared through lexicon jobs.

### 3. Lexicon Voice loading becomes explicit

The voice page currently performs blocking requests for storage policies, recent runs, and run detail without visible loading states. The page will show explicit loading placeholders or messages for:
- policy loading
- recent voice runs loading
- selected run detail loading

This prevents the page from appearing silent or stalled while data loads.

### 4. Policy editing becomes explicit and single-entry

The storage policy list currently supports both radio selection and `Edit policy`, which duplicates intent.

The revised behavior:
- remove radio selection from the policy list
- only show `Edit policy` actions
- only render `Policy Editor` after the operator clicks `Edit policy`
- `Apply` must work even when the operator has not changed fields in the browser, so the action is deterministic and not blocked by a client-side dirty-check assumption

### 5. DB Inspector shows explicit voice paths by scope

DB Inspector will show explicit voice path/resolution information for:
- word audio
- definition audio
- example audio

That applies to words and phrases where those assets exist. The display should distinguish:
- playback route
- resolved storage target/path

### 6. Voice import gets operator-visible progress

`tools/lexicon/voice_import_db.py` will gain progress callback support and counters so both CLI and worker-backed admin jobs can show:
- validation phase progress
- import phase progress
- skip-existing progress labels
- final skipped/failed counts

### 7. Recent voice runs can launch voice import

Recent voice runs in `/lexicon/voice` will include an explicit `Import voice assets` action.

That action deep-links to a new admin voice import page with the manifest path prefilled. It does not autostart.

### 8. History model

Voice import will mirror DB import history behavior:
- current progress card for active job
- current result directly under current progress
- recent jobs section as history

No separate `Last job` panel is needed if recent jobs include timestamp and status.

## API / Backend contract direction

### Import DB

Keep current endpoints and add additive fields through request/result/job payloads.

### Voice import

Add:
- voice import dry-run endpoint
- voice import create-job endpoint
- voice import jobs listed via existing lexicon jobs list filtered by `job_type=voice_import_db`

Request fields mirror DB import:
- `manifest_path`
- `source_reference` optional
- `conflict_mode`
- `error_mode`

## Test strategy

Use TDD by behavior cluster:
1. import-db progress phase counters
2. voice page loading visibility
3. policy editor interaction changes
4. DB inspector voice path rendering
5. voice import CLI/backend dry-run and job behavior
6. voice import admin flow from recent voice runs

Verification layers:
- tool tests
- backend API/job tests
- admin frontend tests
- targeted Playwright smoke for the new operator flow
