# Learner Follow-Up Design: Second Examples, JSON Cleanup, and Instrumentation

**Date:** 2026-03-26

## Problem

The learner phrase-contract and performance slice is now complete, but three follow-up concerns remain open:

1. learner detail currently persists and imports two examples for words and phrases, while the UI usually shows one
2. some lexicon persistence still relies on broad JSON columns outside the learner hot path
3. the recent performance fixes were verified empirically, but the stack still lacks first-class instrumentation for query shape, latency, and render-path cost

These items should not be mixed back into the finished contract-normalization slice because they are product, schema-governance, and observability concerns rather than one bug.

## Goals

1. Define a canonical learner UX for showing two examples where available.
2. Identify and reduce remaining JSON-heavy lexicon storage that still creates maintenance or operator friction outside learner hot paths.
3. Add durable instrumentation so future learner regressions are caught from metrics and logs rather than only from manual Docker profiling.

## Non-Goals

1. Re-open the normalized phrase learner contract work.
2. Rebuild unrelated lexicon review/admin flows.
3. Add premature, high-cardinality observability that is expensive to operate locally.

## Recommended Approach

Split the follow-up into three bounded tracks:

1. learner presentation track:
   decide and implement a two-example display model for both words and phrases without changing the underlying normalized storage again
2. lexicon schema-governance track:
   audit remaining JSON columns and move only the learner-meaningful or operationally queried fields into structured storage
3. instrumentation track:
   add targeted request/query/render instrumentation around learner endpoints and importer/runtime boundaries

This keeps product/UI decisions from being blocked on broader schema cleanup and keeps schema cleanup from being justified only by intuition instead of measured pressure.

## Track 1: Show Two Examples Instead of One

### Current state

- the importer and normalized phrase storage preserve multiple examples
- learner detail views usually surface only the first example
- there is no canonical policy for when two examples should appear, how they should be ordered, or how missing translations should behave

### Product decision

The learner detail contract should support up to two examples per sense/meaning for both words and phrases.

Recommended display rules:

1. show the first example by default when only one exists
2. show the first two examples when two or more exist
3. keep ordering source-defined via `order_index`
4. render example translation directly below each example when available
5. do not invent placeholder translation text when the second example lacks a localized translation

### UI behavior

- word detail:
  each meaning can show up to two example blocks
- phrase detail:
  each sense can show up to two example blocks
- cards/list/range summaries:
  remain unchanged; second-example expansion belongs only to detail surfaces
- compactness:
  preserve the existing stacked example treatment rather than adding a carousel or progressive disclosure first

### API contract impact

No schema change should be required if the existing detail payload already returns ordered examples. This track is primarily:

1. frontend rendering change
2. frontend tests proving two ordered examples render correctly
3. optional backend regression asserting detail endpoints do not truncate to one example in shaping

### Risks

1. detail surfaces can become visually dense on mobile if both examples always render
2. mixed translation availability can create asymmetric example blocks
3. example duplication quality issues become more visible once the second example is shown

### Acceptance criteria

1. word detail renders two examples when two exist
2. phrase detail renders two examples when two exist
3. example translations remain aligned to the matching example
4. one-example data still renders cleanly with no layout regression

## Track 2: Broader Cleanup of Remaining JSON-Heavy Lexicon Tables

### Current state

The learner hot path no longer depends primarily on broad phrase JSON, but JSON-heavy storage still exists elsewhere for provenance, operator workflows, or partially normalized lexicon features.

These JSON fields are not all equally problematic. Some are acceptable provenance blobs; others still hold data that operators or code paths may want to filter, compare, diff, or validate structurally.

### Audit principle

Classify remaining JSON columns into three groups:

1. keep as provenance/debug JSON
2. normalize because they are queried, validated, or rendered meaningfully
3. leave temporarily but put behind typed accessors and documented ownership

### Recommended targets

Prioritize cleanup only where at least one of these is true:

1. the field is used in learner or admin rendering beyond raw inspection
2. the field is queried or filtered in SQL
3. the field is validated across import/export boundaries
4. the field routinely causes test fragility or shape drift

Likely candidates after the learner phrase work:

1. residual phrase/operator payload fragments that are still semantically structured rather than purely archival
2. enrichment or review payload segments that carry durable structured facts but remain embedded as JSON blobs
3. repeated list-like metadata fields that would be better represented as child rows or narrower typed columns

### Migration strategy

Use an audit-first, migration-second approach:

1. document every remaining significant JSON column and its current owner
2. mark each column as `provenance`, `transitional`, or `needs_normalization`
3. normalize only one bounded cluster at a time
4. keep raw JSON only where it adds real replay/debug value

### Acceptance criteria

1. a written JSON-column audit exists with dispositions for each significant field
2. at least one meaningful non-hot-path JSON cluster is either normalized or explicitly kept with rationale
3. importer/export docs name the authoritative storage for each moved field

## Track 3: Stronger Query and Performance Instrumentation

### Current state

Recent learner performance fixes were verified through:

1. direct live API timings
2. Docker CPU sampling
3. targeted smoke tests

That proved the regression and the fix, but it does not provide an ongoing guardrail.

### Recommended instrumentation

Add lightweight, low-risk instrumentation in three layers:

1. request-level timing on learner endpoints
2. targeted query-count / query-duration instrumentation for knowledge-map handlers
3. frontend render timing or debug counters around the most expensive learner detail/range components

### Backend instrumentation

For learner endpoints, record:

1. route name
2. total request duration
3. DB query count
4. DB query duration aggregate
5. result size summary where cheap to compute

Implementation direction:

1. SQLAlchemy event hooks or session-scoped counters for request-local query count and duration
2. structured logs for local/dev visibility
3. optional Prometheus-style counters/histograms later if the stack already has a metrics path

### Frontend instrumentation

Keep frontend instrumentation lightweight and dev-oriented:

1. optional debug timing around range-detail and entry-detail render work
2. no production spam logging by default
3. component-level regression tests where practical for repeated expensive recomputation

### Operator value

After this lands, learner regressions should be diagnosable from:

1. endpoint timings in logs
2. query-count inflation
3. repeatable smoke/e2e timings under the Docker stack

### Acceptance criteria

1. learner endpoint logs include request duration and DB query summary
2. at least one regression test or harness check protects the instrumentation path from silently disappearing
3. local Docker verification can show before/after timing evidence without ad hoc profiling scripts

## Execution Order

Recommended order:

1. instrumentation first
   this makes later JSON cleanup and second-example work easier to measure
2. second-example UI work
   this is product-visible and low migration risk
3. broader JSON cleanup
   do this last because it is the most open-ended and benefits from instrumentation already being present

## Risks

1. JSON cleanup can expand endlessly unless the audit is bounded and disposition-driven
2. second-example rendering can expose content-quality problems that were previously hidden
3. instrumentation can become noisy or expensive if it is not kept route-scoped and low-cardinality

## Deferred Follow-Up After This Follow-Up

1. broader learner detail UX redesign if two-example rendering makes the page too dense
2. export/operator tooling adjustments for any newly normalized non-hot-path JSON clusters
3. dashboarding or metrics backend integration if lightweight structured logs are not enough
