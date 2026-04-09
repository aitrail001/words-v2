# Import Preflight and Manual Dry Run Design

## Goal

Make Import DB operator-driven and predictable by removing automatic dry-run execution on page open, and make dry run/import share a stronger preflight/importability analysis that catches most import-blocking issues before any SQL write attempt.

## Problem

Current behavior has two problems:

1. Opening Import DB from Lexicon Ops can auto-run dry run through `autostart=1`, which surprises operators and starts backend work before they explicitly choose an action.
2. Dry run still relies too much on import-path behavior. It catches some problems, but it is still too close to the real write path and does not clearly separate:
   - schema/content validation
   - conflict/importability analysis
   - actual SQL write execution

The result is that operators can still discover import failures too late, especially for phrase and translation structure problems, and opening the page can already trigger backend work.

## Decision

We will make two coordinated changes:

1. Remove dry-run autostart entirely from the Lexicon Ops -> Import DB flow.
2. Introduce a shared preflight/importability analysis used by both dry run and real import before any SQL write phase starts.

Dry run remains synchronous in the backend request path. Real import remains the only async worker-backed SQL write path.

## Approach Options Considered

### Option 1: Remove autostart and add shared mandatory preflight

This is the chosen option.

- Import DB opens with prefilled context only.
- Dry run is explicit operator action.
- Dry run becomes a true preflight/importability report.
- Real import runs the same preflight before writes.
- If preflight fails, import stops before any SQL mutation.

Why chosen:
- fixes surprising page-open behavior
- keeps operator control explicit
- avoids safety depending on whether someone remembered to run dry run first
- minimizes UI and workflow complexity

### Option 2: Keep autostart but change dry run internals

Rejected.

This would reduce some backend risk but still surprise operators by doing work on open. It solves the wrong half of the problem.

### Option 3: Make dry run mandatory before import

Rejected for now.

This would force workflow order in UI, but it complicates CLI/API usage and adds stateful coupling between dry run and import. Shared mandatory preflight inside import is safer and simpler.

## Target Behavior

### Lexicon Ops

- `Open Import DB` passes input/source context only.
- It does not pass `autostart=1`.
- No dry run is started by navigation.

### Import DB page

- On open, the page shows the prefilled path/reference/language.
- No dry run runs automatically.
- Operator must click `Dry Run` or `Import`.
- Active-job restore remains for real import jobs only.
- Last-job display remains informational only.

### Dry Run

Dry run performs:

1. input/file/artifact sanity checks
2. row parsing and JSONL validity
3. schema/shape validation for words, phrases, and references
4. normalization/content validation for import-blocking fields
5. conflict/importability analysis against current DB state
6. write-plan summary estimation such as likely create/update/skip/conflict/fail counts

Dry run does not:
- enqueue a worker job
- execute SQL writes
- rely on rollback-based shadow import as its primary mechanism

### Import

Import performs:

1. the same shared preflight/importability analysis as dry run
2. if preflight fails, return/import-job fail before any SQL write
3. if preflight passes, continue into the real SQL write/import phase

This means dry run is optional operationally, but preflight is mandatory technically.

## Preflight Coverage

The shared preflight/importability layer should cover the most common import blockers without executing the write path.

### 1. File and artifact sanity

- allowed path root
- file exists and is readable
- JSONL lines parse
- directories contain supported import artifacts

### 2. Schema and shape validation

- required top-level fields exist for each entry type
- expected container types are correct
- nested structures needed by import exist and have valid shapes
- import-blocking required strings are non-empty

Examples include but are not limited to:
- localized translation fields such as `usage_note`
- definition/example strings that import depends on
- phrase/word sense structures

### 3. Normalization/content validation

- normalized identifiers/forms are non-empty
- locale keys and language-dependent structures are sane
- per-parent ordering fields are internally consistent
- obvious duplicate child ordering collisions are detected in the input

### 4. Conflict/importability analysis against DB

Based on `conflict_mode`:
- `fail`: detect rows that already exist and would block import
- `skip`: detect rows likely to skip
- `upsert`: detect whether target rows can be rebuilt safely before writes

### 5. Batch-level write-plan analysis

- classify rows into likely create/update/skip/conflict/fail buckets
- surface unresolved rows as dry-run issues instead of letting them fall into the SQL phase blindly

## Architecture

### Shared import preflight module

Add a shared internal preflight path in `tools/lexicon/import_db.py` that both dry run and real import call.

Conceptually:
- parse rows
- validate rows
- inspect DB for importability/conflicts
- return structured `preflight_summary` + `error_samples`

### Dry run endpoint

The dry-run API should call the shared preflight path and return:
- row summary
- preflight/importability summary
- error samples

No SQL write/import execution should happen here.

### Import endpoint / worker

The real import path should call the same preflight first.
If preflight produces blocking errors, fail immediately before SQL write execution.
If preflight passes, proceed into the current import path.

## Error Handling

- Validation/importability problems should be returned as structured operator-facing errors, not only raw trace strings.
- Real infrastructure/runtime failures during the actual write phase should still fail loudly.
- UI should distinguish:
  - dry-run/preflight issues
  - import execution failures
  - last-job historical failures

## Testing Strategy

### Lexicon tool tests

Add/adjust tests for:
- no-autostart behavior is not relevant here
- dry run uses preflight only and does not execute write path
- import runs preflight before write path
- blocking preflight errors stop import before write path
- words and phrases both covered
- conflict modes reflected in preflight summary

### Backend API tests

Add/adjust tests for:
- dry-run response shape with preflight summary and errors
- import failure before SQL write when preflight fails
- no regressions in job response contracts

### Frontend tests

Add/adjust tests for:
- opening Import DB with prefilled context does not auto-run dry run
- page still allows manual `Dry Run` and `Import`
- dry-run results render preflight findings clearly

### E2E smoke

Targeted smoke should verify:
- Ops navigation opens Import DB without auto-running dry run
- user manually triggers dry run
- UI renders result without worker progress semantics

## Scope Boundaries

Included:
- remove autostart dry run
- shared preflight/importability layer
- dry run behavior change
- import preflight-before-write behavior
- tests/docs/status for this slice

Not included:
- turning dry run into async worker jobs
- full import history UI redesign
- major import job model changes beyond preflight failure handling
- large-schema redesign of lexicon import data

## Risks and Mitigations

### Risk: preflight duplicates too much import logic

Mitigation:
- keep preflight focused on importability and conflict analysis
- avoid reproducing the entire write path
- share reusable validators/classifiers rather than cloning ORM logic

### Risk: false confidence from incomplete preflight

Mitigation:
- document preflight as "most import-blocking issues before write"
- still keep real import error handling strong
- add regression tests for known production failures

### Risk: UI confusion between active job and history

Mitigation:
- keep active import progress and last job separate
- do not auto-run dry run on navigation

## Success Criteria

- Opening Import DB from Ops does not run dry run automatically.
- Dry run is explicit-only.
- Dry run catches known import-blocking validation/importability errors without attempting the real write path.
- Real import runs the same preflight before any SQL mutation.
- Known phrase/translation validation issues fail early.
- Tests cover words and phrases across tool, backend, frontend, and targeted e2e layers.
