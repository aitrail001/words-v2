# Import DB Hardening Design

## Goal

Harden lexicon import for both words and phrases so operators can validate earlier, choose conflict and error handling modes explicitly, see clear job status in the admin UI, and avoid silent or misleading failures.

## Problem Summary

The current import flow has three gaps:
- validation problems can surface in the middle of a long import instead of before writes begin
- phrase reruns can fail during upsert because child graph replacement is not safe under autoflush
- admin UI can show `Waiting for first row...` even when the job already failed before row progress started

## Operator Requirements

1. Update the admin UI to expose import options clearly.
2. Do not fail silently.
3. Verify earlier than the middle of import.
4. If one row fails, provide an option to continue.
5. If a row already exists, provide an option to upsert.
6. Dry run must surface the same issues without DB writes.
7. Apply consistently for both words and phrases.

## Recommended Approach

Use a two-phase import contract shared by admin jobs and the lexicon import code:
- phase 1: preflight validation across all rows
- phase 2: import execution using explicit operator-selected modes

Expose three operator controls:
- `conflict_mode`: `fail | skip | upsert`
- `error_mode`: `fail_fast | continue`
- `dry_run`: `true | false`

This keeps the current import model intact while making validation and failure handling explicit.

## Alternatives Considered

### Option 1: Minimal backend bugfix only
- fix phrase upsert rerun bug
- improve error text in UI
- keep import behavior otherwise unchanged

Pros:
- smallest code change

Cons:
- does not solve early validation or continue-mode requirements
- operators still discover row issues late

### Option 2: Recommended two-phase hardening
- preflight validation before writes
- configurable conflict and error modes
- dry-run uses the same validation phase
- clearer job state and result reporting

Pros:
- addresses the real operator workflow
- still fits the existing job/import architecture
- shared across words and phrases

Cons:
- moderate backend and UI changes

### Option 3: Full staged import pipeline
- explicit validate, plan, execute, commit phases as separate jobs

Pros:
- strongest workflow separation

Cons:
- too large for this slice

## Design

### 1. Shared import modes

Extend the import request contract for both CLI and admin job creation with:
- `conflict_mode`: `fail`, `skip`, `upsert`
- `error_mode`: `fail_fast`, `continue`
- `dry_run`: boolean

Semantics:
- `conflict_mode=fail`: existing entry is an error
- `conflict_mode=skip`: existing entry is skipped and counted
- `conflict_mode=upsert`: existing entry is updated in place
- `error_mode=fail_fast`: stop on first row error
- `error_mode=continue`: keep processing later rows and record row failures
- `dry_run=true`: run validation and import planning logic without commit/write side effects

### 2. Preflight validation

Before import execution, scan input rows and validate:
- compiled row schema/contract
- word/phrase-specific required fields
- localized translation payload rules
- import mode invariants if needed

This phase should catch content problems such as empty `translations.<locale>.usage_note` values before row mutation begins.

Output from validation should include:
- total rows scanned
- valid row count
- invalid row count
- sample errors
- optional artifact path for full row error ledger

Dry-run should stop after this phase if validation fails, and if validation passes should return the import plan/summary without committing writes.

### 3. Execution with row-level failure handling

During real import:
- `fail_fast`: throw immediately on row error
- `continue`: record per-row errors, keep importing valid rows, and complete with an error summary

Execution result should return:
- processed row count
- created/updated/skipped counts
- failed row count
- sample error rows
- optional error artifact path
- final outcome: `completed`, `completed_with_errors`, or `failed`

### 4. Phrase upsert safety

Fix phrase rerun/upsert by rebuilding phrase child graphs safely:
- for existing phrase upserts, clear/delete existing `phrase_senses` and dependent rows before inserting replacements
- perform rebuild under `session.no_autoflush`
- preserve deterministic order indices

This should make reruns safe for both dry-run simulation and real upsert execution.

### 5. Admin UI behavior

Update `/lexicon/import-db` to show:
- import options form
  - conflict handling
  - error handling
  - dry run toggle
- richer job state copy
  - if failed before first row: show `Failed before first row`
  - show backend error summary directly
- completion summaries
  - imported/skipped/failed counts
  - validation failures and sample errors
  - artifact paths if available

The UI should not imply progress exists when the job already failed.

### 6. Status model

Keep the persisted job status model stable if possible, but expose richer meaning in result payload:
- validation summary
- execution summary
- error samples
- completion mode

If backend status enum must remain `queued | running | completed | failed`, then `completed_with_errors` should be represented through `status=completed` plus result payload flags.

## Data Flow

1. Admin or CLI submits import request with modes.
2. Backend job starts and records `running` state.
3. Preflight validation scans all rows.
4. If validation hard-fails:
- job becomes `failed`
- payload includes validation summary/errors
5. If dry-run and validation passes:
- job completes with plan/summary only
6. If apply mode:
- execution processes rows under selected conflict/error modes
- row failures are accumulated or raised depending on `error_mode`
7. Admin UI polls job and renders meaningful summary.

## Testing Strategy

### Backend/tool tests
- word validation failure is caught in preflight before import mutation
- phrase validation failure is caught in preflight before import mutation
- dry-run surfaces the same issues as real import preflight
- `error_mode=continue` completes with row failures recorded
- `conflict_mode=skip` skips existing rows
- `conflict_mode=upsert` updates existing rows
- phrase rerun with upsert no longer violates `(phrase_entry_id, order_index)`

### Frontend tests
- import options render and submit correct payload
- failed-before-first-row jobs show failure text, not waiting text
- completed-with-errors summary renders counts and errors

### E2E smoke
- create import job from admin with dry-run against a fixture
- verify options are passed and result summary renders
- verify failed early import shows explicit failure state

## Risks

- preflight validation can duplicate logic if not shared carefully with row import validation
- continue-mode imports need clear operator messaging to avoid partial-import confusion
- phrase graph replacement must remain safe for both ORM-backed and fake-session tests

## Recommendation

Implement the two-phase import hardening with explicit operator modes, shared across words and phrases, and include the phrase upsert fix plus the admin UI status correction in the same slice.
