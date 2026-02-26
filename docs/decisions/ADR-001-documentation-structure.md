# ADR-001: Documentation Structure for Rebuild

**Status**: ACCEPTED
**Date**: 2026-02-26
**Decision Makers**: jzhang

## Context

Starting a full rebuild of Words-Codex. The prototype had lessons learned scattered across conversations and a single `LESSONS_LEARNED.md`. Plans existed only in chat history. Need a structured approach to capture decisions, plans, and lessons as the rebuild progresses.

## Decision

Adopt a `docs/` directory with four subdirectories:
- `plans/` — Implementation plans (dated)
- `decisions/` — Architecture Decision Records (numbered)
- `lessons/` — Lessons learned (dated)
- `api/` — API documentation

Rules added to `CLAUDE.md` to enforce documentation at key moments (before implementing, when deciding, when something breaks, after completing a phase).

## Consequences

**Positive**:
- Plans are reviewable and trackable (status headers)
- Decisions have context preserved (ADRs never deleted)
- Lessons are captured immediately, not retroactively
- Future sessions can reference docs instead of re-discovering context

**Negative**:
- Small overhead per phase (writing docs)
- Must discipline ourselves to update status headers

## Alternatives Considered
- Single CHANGELOG.md — too flat, mixes concerns
- Wiki — external to repo, falls out of sync
- No structure — what the prototype did, led to lost context
