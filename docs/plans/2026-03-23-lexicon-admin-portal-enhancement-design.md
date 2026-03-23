# Lexicon Admin Portal Enhancement Design

**Date:** 2026-03-23
**Owner:** Codex
**Status:** Approved

## Goal

Ship one bounded admin-portal enhancement that:

- fixes the compiled-review materialize `500`
- aligns Compiled Review and JSONL Review under a shared lexicon review workspace
- groups Lexicon Ops tracked artifacts by stage and purpose
- upgrades DB Inspector so imported entries read like browseable records instead of shallow summaries

## Why This Slice

The current admin lexicon surfaces work, but they still behave like adjacent tools rather than one workflow:

- Compiled Review has a materialize failure and a cramped list/detail layout
- JSONL Review and Compiled Review present similar information with different UI structure
- Lexicon Ops shows tracked artifacts as a flat filename list instead of operator stages
- DB Inspector browsing exists, but detail is too shallow for import verification

The portal needs a shared interaction language without broad route churn.

## Chosen Approach

Use a bounded version of the “shared admin shell” approach:

- keep existing routes and backend ownership
- add shared lexicon-only frontend workspace primitives
- extend backend contracts only where the touched pages need more structured data
- keep import-db semantics and file contracts stable

This gives the long-term shape benefits of a unified portal while staying small enough to ship as one enhancement.

## Architecture

### Shared Lexicon Workspace

Create a shared workspace pattern for:

- `admin-frontend/src/app/lexicon/compiled-review/page.tsx`
- `admin-frontend/src/app/lexicon/jsonl-review/page.tsx`
- `admin-frontend/src/app/lexicon/db-inspector/page.tsx`
- the tracked-artifact section of `admin-frontend/src/app/lexicon/ops/page.tsx`

Common structure:

- context/header band
- horizontal top rail for batch or entry-family navigation
- paged left rail for entries or records
- wide detail workspace
- consistent metadata, structured detail, raw JSON, and action panels

The workspace is lexicon-specific, not a general admin-app shell refactor.

### Backend Boundaries

Backend changes stay incremental:

- fix materialization in `backend/app/api/lexicon_compiled_reviews.py`
- expand inspector detail in `backend/app/api/lexicon_inspector.py`
- optionally expose grouped artifact metadata from `backend/app/api/lexicon_ops.py` if frontend-only grouping proves too brittle

No route URL changes are required.

## Page Behavior

### Compiled Review

- batches move to a horizontal rail with browse controls
- selecting a batch loads a paged entry rail capped at `10` items per page
- the main workspace shows:
  - entry summary
  - validator/QC panels
  - structured lexical detail panels
  - full-width raw compiled JSON
  - decision panel aligned with the detail workspace

Materialize continues to produce:

- `review.decisions.jsonl`
- `approved.jsonl`
- `rejected.jsonl`
- `regenerate.jsonl`

but the write path must normalize exported rows before JSON serialization and fail with operator-usable errors instead of an opaque `500`.

### JSONL Review

Move JSONL Review onto the same workspace pattern while preserving file-backed behavior:

- same overall list/detail layout
- same decision-panel language
- same raw JSON placement
- preserve JSONL-only warnings, review summary, and sidecar-path handling

### Lexicon Ops

Replace the flat tracked-artifact list with flow-aligned stage groups:

- base inventory
- adjudication
- enrichment
- compiled review inputs
- reviewed outputs
- import verification

Within each stage, show purpose groups where applicable:

- word
- phrase
- reference
- shared/ledger

This makes the page reflect the operator workflow rather than raw filenames.

### DB Inspector

Keep search and browse, but make detail feel like browsing a complete entry:

For words:

- top-level identity, provenance, CEFR, rank, phonetics
- one definition panel per meaning
- examples nested under the meaning panel
- relations nested under the meaning panel
- enrichment/provenance evidence in its own panel

For phrases and references:

- top-level fields first
- structured subpanels after
- consistent panel language with the review pages

## Error Handling

### Compiled Review Materialize

The current issue is likely specific to the DB-backed compiled-review path, not the file-backed JSONL review path.

Compiled Review currently rebuilds JSONL rows from ORM-backed review items and serializes them directly. That path needs defensive normalization before writing JSONL.

Expected improvements:

- JSON-safe row normalization before write
- explicit `4xx` for safe-path and operator-correctable failures
- preserve existing output filenames and write locations

### JSONL Review

JSONL Review already goes through the file-backed review materializer service. The enhancement should preserve its existing behavior and add regression coverage proving it does not share the compiled-review failure mode.

## Testing Strategy

### Backend

- add a failing regression test for compiled-review materialize covering the current failure mode
- keep JSONL review materialize covered to prove non-regression
- extend inspector API tests for richer detail payloads
- extend ops API tests if grouped artifact metadata becomes backend-driven

### Frontend

- Compiled Review page tests for:
  - horizontal batch rail behavior
  - paged entry list behavior
  - wide raw JSON/detail layout behavior
- JSONL Review page tests for:
  - shared workspace rendering
  - layout parity with Compiled Review
- DB Inspector page tests for:
  - richer word detail rendering
  - family-specific detail panels
- Ops page tests for:
  - stage grouping
  - purpose grouping

### Verification

- targeted backend pytest for compiled review, JSONL review, inspector, and ops
- targeted admin frontend Jest suites for the touched pages and shared components
- targeted Playwright smoke if the local stack remains practical in this environment

## Out Of Scope

- changing route URLs
- redesigning import-db semantics
- redesigning unrelated admin pages
- changing lexicon artifact contracts beyond safe compiled-review materialize normalization and additive display data

## Risks And Controls

### Risk: shared-shell scope creep

Control:

- keep the shared components lexicon-only
- migrate only the pages in this request

### Risk: backend/frontend contract drift

Control:

- keep contracts additive where possible
- preserve existing route calls and action names

### Risk: regression in review/export flows

Control:

- start with failing regression tests
- verify compiled and JSONL materialize behavior separately

