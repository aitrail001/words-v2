# Local Data-Only Lexicon Policy Design

Date: 2026-03-23
Owner: Codex

## Goal

Keep the repository code checkout easy to fast-forward after merges by treating `data/` as local operational storage rather than Git-synced project content.

## Problem

Long-running lexicon jobs write mutable sidecars and compiled outputs under `data/lexicon/snapshots/...`.
Some of those files were still tracked in Git, which made local code sync ambiguous and allowed a stale checkout to keep running old code after remote merges.

## Decision

- Treat all of `data/` as local-only operational storage.
- Keep `.gitignore` covering `data/`.
- Remove existing tracked `data/` files from Git control while leaving them on disk locally.
- Continue using `data/lexicon/...` as the default local path structure for snapshots, benchmarks, reports, and reviewed CSV inputs.

## Why This Option

This is the simplest operator model:

- code sync is separate from runtime artifacts
- `git fetch` / `git pull --ff-only` can update code without pretending data artifacts are source-controlled state
- long-running enrichment jobs no longer dirty tracked files

## Tradeoffs

- snapshot artifacts, benchmark outputs, reviewed CSV inventories, and audit files under `data/` no longer sync through Git
- operators must manage local backups/export intentionally when data matters outside one machine

## Out of Scope

- introducing a runtime copy workflow
- auto-syncing local data artifacts to remote storage
- changing backend/runtime default paths away from `data/lexicon/...`
