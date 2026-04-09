# ADR-001: Documentation Structure for Rebuild

**Status:** SUPERSEDED  
**Date:** 2026-02-26  
**Updated:** 2026-04-08  
**Decision Makers:** jzhang

## Context

This ADR established the first documentation structure during the rebuild. It was useful at the time, but the repo has since grown beyond the original `plans / decisions / lessons / api` shape.

The live docs tree now includes `reports`, `prompts`, `status`, `runbooks`, `superpowers`, and an archive need. The repo also no longer uses `docs/api/` as a current top-level documentation area.

## Original decision

The original rebuild documentation structure introduced `docs/` with these subdirectories:

- `plans/`
- `decisions/`
- `lessons/`
- `api/`

## Why this ADR is superseded

The current repo structure and current working practice no longer match the original decision closely enough:

- `docs/README.md` now maps the actual live structure
- long evidence belongs in `docs/reports/`, not the status board
- historical material needs `docs/archive/`
- reusable prompt templates are distinct from one-off historical prompts
- `docs/api/` is not the current organizing center for documentation

## Current replacement

Use `docs/README.md` as the current documentation map and operating contract.

The current live structure is:

- `archive/`
- `decisions/`
- `lessons/`
- `plans/`
- `prompts/`
- `reports/`
- `runbooks/`
- `status/`

## Consequences

Positive:
- current truth is easier to find
- historical material is less likely to pollute active work
- the status board can stay concise
- reports and runbooks have clear separate roles

Negative:
- some older docs must be moved or relabeled
- old references to `docs/api/` must be cleaned up
