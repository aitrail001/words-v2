# ADR-003: Lexicon Review Staging In Main Stack

**Status:** ACCEPTED  
**Date:** 2026-03-08

## Context

The lexicon tool now produces grounded deterministic selections and optional bounded rerank outputs, but large-scale human review should not happen by inspecting raw JSONL files. The project also plans an admin system, yet the current worktree does not contain `admin-frontend/`.

We need a review architecture that:

- keeps lexicon generation as an offline/admin workflow
- supports auto-routing and auto-accept for most lexemes
- supports targeted human review for flagged words
- preserves full provenance for WordNet candidates, deterministic ranking, rerank output, reviewer comments, and final decisions
- avoids direct mutation of learner-facing tables before approval

## Decision

Use the main project stack as the future home for lexicon review, but keep review data in a separate staging layer before publish.

Concretely:

- keep the lexicon generator under `tools/lexicon/`
- generate machine-readable decision artifacts such as `selection_decisions.jsonl`
- import those artifacts into separate review staging tables or a separate review schema in the same Postgres instance
- defer admin review UI implementation until the rebuild includes `admin-frontend/`
- keep publish into learner-facing tables as a separate explicit step

## Consequences

### Positive

- avoids painful raw JSONL review workflows
- reuses the future backend/admin/auth/audit stack
- keeps published learner-facing data isolated from experimental lexicon runs
- preserves full provenance and review history
- supports automatic first-pass rerank and only targeted human review

### Negative

- requires future backend staging models and APIs
- delays human review UI until admin frontend work begins
- introduces another content state transition (`generated -> staged -> approved -> published`)

### Operational implications

- same DB instance is the default recommendation
- separate staging tables or schema should be used
- raw snapshot or decision-artifact writes should not bypass review staging when review gating is required
- compiled import after review/approval remains the canonical final learner-enrichment landing path until staged review publish delegates to the same importer semantics

## Related Documents

- `docs/plans/2026-03-07-lexicon-tool-design.md`
- `docs/plans/2026-03-08-lexicon-review-staging-design.md`
- `docs/plans/2026-03-08-lexicon-review-staging-implementation.md`
