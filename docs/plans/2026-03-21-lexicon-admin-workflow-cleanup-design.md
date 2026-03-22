# Lexicon Admin Workflow Cleanup Design

**Date:** 2026-03-21

## Goal

Streamline the admin lexicon tool so the current workflow is obvious:

1. start from snapshot operations
2. choose a review mode
3. export or materialize approved JSONL
4. import approved JSONL into the final lexicon DB
5. verify the final DB state

The current admin surface mixes an older `selection_decisions.jsonl` review workflow with newer compiled-artifact review tools. That makes the portal harder to understand than the underlying pipeline.

## Current State

The admin tool currently has four overlapping surfaces:

- `/lexicon`
  - legacy staged review import for `selection_decisions.jsonl`
  - legacy staged review queue and publish flow
  - embedded DB inspector
- `/lexicon/ops`
  - snapshot folder catalog and artifact inspection
- `/lexicon/compiled-review`
  - compiled JSONL review backed by review staging tables
- `/lexicon/jsonl-review`
  - compiled JSONL review backed by sidecar decisions JSONL

This splits the operator’s mental model across old and new flows:

- the old staged review UI is still treated like the main lexicon portal
- the DB inspector is buried inside the legacy route
- Lexicon Ops shows snapshot readiness but cannot launch the next workflow directly
- final `import-db` is still CLI-only even though it is part of the operator workflow

## Design Principles

- Preserve both compiled review modes.
- Keep JSONL as the review artifact boundary.
- Keep final DB import explicit and separate from review approval.
- Make Lexicon Ops the workflow hub, not the only entrypoint.
- Keep standalone pages for operators who want to load artifacts directly.
- Demote the old selection-review flow to a clearly labeled legacy surface.

## Recommended Information Architecture

### Primary routes

- `/lexicon/ops`
  - workflow hub
  - snapshot-first operations
- `/lexicon/compiled-review`
  - standalone compiled-review DB staging workflow
- `/lexicon/jsonl-review`
  - standalone JSONL-only review workflow
- `/lexicon/import-db`
  - standalone final import workflow
- `/lexicon/db-inspector`
  - standalone final DB verification workflow
- `/lexicon/legacy`
  - deprecated selection-review workflow

### Navigation labels

- `Lexicon Ops`
- `Compiled Review`
- `JSONL Review`
- `Import DB`
- `DB Inspector`
- `Legacy`

The existing `Lexicon Review` top-level nav item should stop pointing at the legacy mixed page. It should either:

- point to `/lexicon/ops`, or
- be renamed to `Legacy`

The recommended path is to point primary lexicon navigation to `/lexicon/ops`.

## Route Responsibilities

### Lexicon Ops

Lexicon Ops becomes the default operator workflow page.

It should:

- list snapshot directories
- show artifact presence and row counts
- show a selected snapshot’s important files
- surface action buttons for the selected snapshot:
  - `Open Compiled Review`
  - `Open JSONL Review`
  - `Open Import DB`
  - `Open DB Inspector`
- prefill those pages using query parameters derived from the selected snapshot
- include an embedded final-import panel for snapshot-driven operators

The embedded import panel should support:

- selected input artifact path
- optional source reference override
- dry-run summary
- explicit import action
- result summary

### Compiled Review

Keep it as a standalone page.

It should continue to support:

- manual file upload
- batch list
- review decisions
- approved/rejected/regenerate/decisions export

It should also accept query parameters from Lexicon Ops so the operator can open it with snapshot context prefilled.

### JSONL Review

Keep it as a standalone page.

It should continue to support:

- direct artifact path entry
- optional decisions path
- optional output directory
- sidecar decision editing
- materialization

It should also accept query parameters from Lexicon Ops to prefill artifact, decisions, and output locations.

### Import DB

Add a standalone page for operators who want to run final import directly.

It should support:

- direct input path entry
- optional source reference
- optional language
- dry-run summary using the exact import logic
- explicit import execution
- import result summary

This page is operationally distinct from review and should remain explicit.

### DB Inspector

Extract the DB inspection surface from the old `/lexicon` page into its own standalone page.

It should be framed as:

- final-state verification
- inspection of already imported rows
- not part of review staging

### Legacy

Move the old staged selection-review workflow to `/lexicon/legacy`.

This page should be clearly marked:

- deprecated
- older review path
- no longer the primary lexicon workflow

The goal is to preserve access without letting it compete with the compiled-review tools.

## Backend/API Changes

### Existing APIs to keep

- `GET /api/lexicon-ops/snapshots`
- `GET /api/lexicon-ops/snapshots/{snapshot}`
- compiled-review endpoints
- JSONL-review endpoints

### New API surface

Add admin import endpoints under a dedicated resource, for example:

- `POST /api/lexicon-imports/dry-run`
- `POST /api/lexicon-imports/run`

These endpoints should:

- accept an artifact path plus optional import metadata
- validate the path against safe allowed roots
- load the compiled rows from the artifact
- dry-run by summarizing row families and import counts
- execute the same final import code path used by the CLI

The API should stay internal-admin style and can return flat JSON responses rather than a public API envelope.

### Path handling

The import endpoints should reuse the same safe path discipline already used by JSONL review:

- allow repo-relative paths and safe container-visible absolute paths
- reject paths outside the repo root or configured snapshot root
- never execute arbitrary shell commands from operator input

## Shared Data Flow

### Snapshot-first flow

1. operator opens `/lexicon/ops`
2. selects snapshot
3. launches one of:
   - compiled review
   - JSONL review
   - import DB
   - DB inspector
4. page opens with snapshot-derived values prefilled

### Review to final import flow

1. review compiled artifact
2. export or materialize approved JSONL
3. open Import DB
4. dry-run approved JSONL
5. run import
6. open DB inspector to verify final state

This keeps review and final write boundaries explicit while still making the end-to-end workflow feel coherent.

## Security and Operational Constraints

- All new admin endpoints stay admin-authenticated.
- File/path input must be whitelisted to safe roots.
- Final import remains explicit; no auto-publish from review actions.
- The API must call import logic directly, not shell out to arbitrary CLI commands from user input.
- Dry-run and import result messages should not leak filesystem details beyond intended operator paths.

## Testing Strategy

### Frontend

- nav updates
- Lexicon Ops snapshot action buttons and query-prefill behavior
- standalone Import DB page behavior
- DB Inspector standalone route behavior
- Legacy route behavior

### Backend

- import dry-run endpoint path validation
- import execution endpoint path validation
- successful dry-run summary for compiled artifacts
- successful import execution summary
- rejection of unsafe paths

### End-to-end

- snapshot-first launch from Lexicon Ops into JSONL Review
- snapshot-first launch from Lexicon Ops into Compiled Review
- snapshot-first dry-run/import path through Import DB
- standalone route access for Compiled Review, JSONL Review, Import DB, DB Inspector, Legacy

## Non-Goals

- replacing the review DB-backed compiled-review workflow
- removing legacy backend code in this slice
- adding auto-import after approval
- redesigning the lexicon enrichment pipeline itself

## Implementation Notes

- Prefer extracting shared UI sections from the existing `/lexicon` page instead of duplicating DB inspector code.
- Keep the standalone review pages functional without Lexicon Ops.
- Keep query-prefill optional so direct access still works.
