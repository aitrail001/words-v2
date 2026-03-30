# Voice Import Runtime-First Design

## Goal

Harden lexicon voice import so large manifests can finish reliably under worker time limits, while keeping the operator workflow understandable and avoiding storage-policy rewrites during import.

## Scope

This design covers:
- `tools/lexicon/voice_import_db.py`
- worker/job progress reporting for `voice_import_db`
- admin pages for [`/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/voice-import/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/voice-import/page.tsx) and [`/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/import-db/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/import-db/page.tsx)
- DB inspector voice asset presentation in [`/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/db-inspector/page.tsx`](/Users/johnson/AI/src/words-v2/.worktrees/feat_voice_import_runtime_20260330/admin-frontend/src/app/lexicon/db-inspector/page.tsx)
- refreshed storage-policy display behavior

This design does not merge the import pages into one route and does not introduce policy recomputation jobs.

## Constraints

- `Lexicon Voice Import` and `Lexicon Import to Final DB` remain separate pages.
- Voice import keeps the existing admin `error handling` options.
- Default operator behavior should optimize for `error_mode=continue`.
- Voice import must update asset-level fields such as `relative_path` and voice metadata, but must not rewrite storage policy `kind` / `base`.
- Playback URL and resolved storage target remain runtime-derived from DB state.
- A word or phrase can contain many definition and example rows; the import unit must respect that structure.

## Current Problems

1. `voice_import_db` currently validates the full manifest, then in `continue` mode still accumulates successful row changes in one long transaction and commits at the end of the run.
2. A long run can fail in the middle with `SoftTimeLimitExceeded`, losing a large amount of already-processed work.
3. The current importer still touches default storage-policy rows when importing voice assets, even though the intended steady-state model is that policy is managed separately.
4. `voice-import` and `import-db` pages are separate, but their layout diverges enough that operators see overlapping controls without a clearly consistent mental model.
5. DB inspector currently exposes voice details, but not in the requested single horizontal row shape that combines relative path, resolved URL, and playback affordance.

## Decision Summary

### 1. Keep separate import pages

The routes stay separate:
- `/lexicon/import-db`
- `/lexicon/voice-import`

They should share layout patterns and reusable field/result components where possible, but not merge into a tabbed or combined page.

### 2. Use lexical-group commits for voice import

The voice importer will:
1. preflight the entire manifest
2. build lexical groups
3. process one lexical group at a time
4. commit after each group

Lexical group means:
- for `entry_type=word`: the word asset row plus all definition/example rows that belong to that word
- for `entry_type=phrase`: the phrase asset row plus all definition/example rows that belong to that phrase

This is intentionally not raw per-row commit. The commit unit is one lexical entry with all of its child voice rows.

### 3. Allow partial success inside a lexical group

When `error_mode=continue`:
- a failed definition/example row inside a word/phrase group does not roll back successful sibling rows
- the group still commits at the end
- failures are counted and surfaced explicitly

This means a group can end in a mixed state:
- some assets created or updated
- some rows skipped
- some rows failed

That tradeoff is intentional because the user priority is runtime resilience and finishing the manifest.

### 4. Voice import stops mutating storage policy rows

Voice import should no longer create or rewrite default storage-policy rows during normal asset import.

Instead:
- the importer resolves the matching lexical target
- the importer finds or updates the corresponding `LexiconVoiceAsset`
- the importer updates asset fields only, especially `relative_path`
- the importer leaves storage-policy `kind` / `base` unchanged

Refreshing “current DB storage policies” therefore means refreshing the UI from DB, not recomputing or reapplying policy values to assets.

### 5. URL and storage target remain runtime-derived

The system should continue to construct playback/resolved targets at read time from:
- `LexiconVoiceAsset.relative_path`
- linked storage policy values

No background recomputation pass is needed for this request.

## Runtime Model

### Preflight phase

Preflight still validates the full manifest before any writes.

If preflight fails:
- the import fails early
- the job result shows the validation failures
- no asset writes occur

### Group building

After preflight passes, rows are grouped by a deterministic lexical key.

Required properties in the grouping key:
- `entry_type`
- normalized lexical text (`word` / phrase text)
- `language`

Rows within a group are then processed in stable order:
1. word/phrase scope
2. definition scope
3. example scope
4. original manifest order as final tie-breaker

This ordering keeps parent targets available before their dependent rows are resolved.

### Group execution

For each group:
- start a transaction
- process every row in the group
- record created/updated/skipped/failed counters
- commit the transaction once

For `error_mode=continue`:
- row-level failures are captured and counted
- processing continues to the next row in the same group
- successful rows remain eligible for commit

For `error_mode=fail_fast`:
- the first runtime error in the group aborts the job
- the current group transaction rolls back
- previously committed groups remain durable

### Time-limit resilience

Because each group commits independently:
- completed groups survive `SoftTimeLimitExceeded`
- retries only need to finish the remaining groups
- progress labels can point to the current lexical group instead of one giant transaction

## Data Contract Changes

### Voice import asset behavior

The importer updates:
- `relative_path`
- MIME / audio format fields
- asset-level voice metadata fields already stored on `LexiconVoiceAsset`, including provider, family, voice id, profile key, status, and generation metadata
- timestamps and status/error fields

The importer does not update:
- storage policy base roots
- storage policy storage kinds
- fallback storage policy values

Hard rule:
- voice DB import must not touch storage-policy rows
- the required steady-state behavior is asset-relative-path updates only, plus normal asset metadata updates

### Job progress behavior

Voice job progress should expose:
- validating vs importing phase
- validated rows
- imported rows
- skipped rows
- failed rows
- total rows
- current lexical-group label

The UI should keep using additive counters and not infer state from a single progress number.

### Recent jobs behavior

Recent jobs remain history for the page, but the design expects paging or dedicated browsing once the list becomes too shallow for real operator use.

## UI Design

### Import pages

`/lexicon/import-db` and `/lexicon/voice-import` stay separate pages but should converge on the same operator structure:
- top form
- current progress
- current result
- recent jobs/history

The overlapping fields can share presentation components, but each page keeps its own route, job type, and page copy.

### Voice import page

The page should continue to expose:
- manifest path
- language
- conflict handling
- error handling
- dry run
- import

It should also support better browsing of recent jobs when the current six-row view becomes insufficient.

### DB inspector voice rows

DB inspector should render each voice asset as one full-width horizontal row.

Each row includes:
- scope (`word`, `definition`, `example`)
- one combined asset block that shows both:
  - relative path
  - resolved URL
- play button

The relative path and resolved URL should stay together in the same row body rather than being split into separate columns/cards.

## Storage Policy Display

The storage policy screen should refresh its displayed values from the current DB state.

For this task, that means:
- read-only or clearly separated policy display behavior
- no implication that voice import edits policy roots
- no recomputation step

If policy editing remains available elsewhere, it should remain a distinct operator action from voice import.

## Error Handling Semantics

### `error_mode=continue`

- continue processing after row failures
- count failed rows
- keep successful rows in the current lexical group
- commit the group at the end

### `error_mode=fail_fast`

- stop on the first runtime error
- roll back only the current uncommitted lexical group
- preserve all previously committed groups

## Testing Strategy

### Tool tests

Add tests for:
- grouping rows by lexical target
- stable in-group ordering
- partial-success commit behavior for `error_mode=continue`
- rollback behavior for `error_mode=fail_fast`
- asset-only updates that leave storage-policy roots unchanged

### Backend/job tests

Add tests for:
- progress summary by phase and lexical group
- durable counts after mid-run row failures
- job failure semantics when a group aborts

### Admin frontend tests

Add tests for:
- separate pages still rendering the parallel import structure
- recent voice jobs browsing behavior, including the expanded history path when the inline list is insufficient
- DB inspector horizontal voice rows with relative path, resolved URL, and play control

### E2E / smoke

Add or update targeted operator coverage for:
- recent voice run -> voice import page
- voice import -> durable progress
- DB inspector -> voice asset playback/path visibility

## Risks

1. Grouping keys that are too loose can merge unrelated rows; grouping keys that are too strict can split one lexical entry incorrectly.
2. Partial success inside a group means operators can see a word/phrase with incomplete audio coverage after one run; this is accepted by design.
3. Removing policy mutation from import requires a clear migration path for any tests or fixtures that currently depend on importer-created default policies.

## Recommended Implementation Order

1. Refactor `voice_import_db` grouping and commit model.
2. Remove storage-policy mutation from voice import and update tests.
3. Update worker progress reporting to use lexical-group-aware labels/counters.
4. Align admin voice import page with the runtime-first job model.
5. Update DB inspector voice row rendering.
6. Add recent-jobs browsing improvements if the page still truncates too aggressively.
