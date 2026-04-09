# ADR-003: Lexicon Review Staging in Main Stack

**Status:** SUPERSEDED  
**Date:** 2026-03-08  
**Updated:** 2026-04-08

## Context

This ADR captured an earlier lexicon review-staging architecture while the operator/admin path was still forming. At that time it explicitly assumed the current worktree did not contain `admin-frontend/`.

That assumption is no longer true. The repo now contains a dedicated `admin-frontend/` app, separate admin routes, and a more evolved operator surface.

## What remains useful

The durable idea behind this ADR is still valid:

- keep offline/admin lexicon generation separate from learner-facing runtime flows
- preserve provenance and reviewability
- avoid unsafe direct writes into learner-facing tables before approval

## Why this ADR is superseded

It is no longer the right current architecture guide because:

- `admin-frontend/` now exists
- the current operator surface is documented in `tools/lexicon/README.md`
- older staged-review assumptions do not fully describe the current compiled-review / JSONL-review / import / inspector flow

## Current replacement

Use these as the current references:
- `tools/lexicon/README.md`
- current backend lexicon routes under `/api/lexicon-*`
- current admin/operator runbooks and status summary

Keep this ADR only as historical context for how the lexicon staging approach evolved.
