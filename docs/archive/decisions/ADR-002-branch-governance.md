# ADR-002: Branch Governance

**Status:** ACCEPTED  
**Date:** 2026-02-27  
**Updated:** 2026-04-08

## Context

This repository uses GitHub branch governance to block regressions before merge and to support promotion from `main` toward pre-prod and production.

The repo now includes:
- CI on `main`
- deploy-preprod and promote-prod workflows
- a pre-prod readiness rehearsal workflow
- rollback and real pre-prod verification runbooks

The exact names of emitted check contexts may evolve as workflows change, so the decision should focus on governance rules, not hard-coded historical check names.

## Decision

1. Use GitHub Rulesets as the single source of truth for `main` merge controls.
2. Keep required checks aligned to the exact check context names currently emitted by CI.
3. Keep CI fail-fast where practical; smoke should block obvious regressions early.
4. Keep deeper test lanes available for broader confidence, especially for review/admin flows.
5. Treat release promotion as a separate governed path from normal PR merge.
6. Keep rollback documentation current whenever promotion mechanics change.

## Current implications

As of the current repo shape:
- backend, learner frontend, admin frontend, and E2E all participate in CI
- the smoke lane is the primary fail-fast PR gate
- promotion workflows exist but still depend on real infra command/URL wiring

## Consequences

Positive:
- merge safety is centralized
- CI naming can evolve without rewriting branch protection in multiple places
- release and rollback steps remain documented alongside governance

Negative:
- workflow renames require ruleset updates
- promotion readiness still depends on environment wiring outside the repo
