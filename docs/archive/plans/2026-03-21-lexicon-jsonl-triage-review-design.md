# Lexicon JSONL Triage Review Design

Date: 2026-03-21
Status: Approved for implementation

## Goal

Improve the JSONL-only lexicon review tool so a human reviewer can make fast publish-safety and semantic-quality decisions without reading raw JSON for every row, while keeping compiled JSONL artifacts and `review.decisions.jsonl` sidecars as the only source of truth.

## Decision

The JSONL-only review route should become a safety-first triage console, not just a file viewer.

The tool should:

1. Let the machine catch obvious structural problems.
2. Surface machine-readable warnings and triage signals in the UI.
3. Present a reviewer summary first.
4. Keep raw JSON as supporting evidence, not the default reading mode.

## Why

The current file-backed review path is operationally correct but cognitively inefficient. Reviewers can inspect and decide rows, but they must read too much raw structure to find the few rows that actually need attention.

The right interaction model is:

1. Quick approval for normal rows.
2. Risk-first inspection for suspicious rows.
3. Raw JSON available for disputes, edge cases, and final confirmation.

## Source Of Truth Boundary

The source of truth remains file-based:

1. Compiled artifact JSONL is immutable input.
2. `review.decisions.jsonl` is the only review overlay.
3. Materialized outputs still come from:
   - compiled artifact
   - decisions sidecar

No review-state migration or database staging is added by this slice.

## Review Model

### Machine-owned checks

The backend already validates obvious structural issues when loading a compiled artifact. This slice should make those results visible to the reviewer instead of hiding them behind load failures or requiring manual JSON inspection.

The machine should surface:

1. Structural warnings
   - missing expected fields
   - wrong field shapes
   - suspicious empty lists
   - odd entity/category combinations
2. Triage metadata
   - warning count
   - warning labels
   - review priority bucket
3. Reviewer summary
   - entry identity
   - lightweight semantic preview
   - provenance summary

### Human-owned checks

Humans still decide:

1. Is this semantically correct enough for learners?
2. Is there any obvious publish risk even if the row is schema-valid?
3. Does this need regeneration or rejection?

## UI Shape

### Queue-first layout

The default experience should be a triage queue:

1. Left column
   - searchable row list
   - warning chips
   - review status
   - triage sort order
2. Main panel
   - reviewer summary first
   - decision controls
   - raw JSON below

### Reviewer summary

The reviewer summary should expose the highest-signal fields first:

1. `display_text`
2. `entry_id`
3. `entry_type`
4. `normalized_form`
5. `frequency_rank`
6. `cefr_level`
7. `entity_category`
8. `source_provenance`
9. counts for:
   - senses
   - forms
   - confusable words

It should also provide a compact semantic preview:

1. first few sense labels or gloss-like cues when available
2. phrase/reference-specific preview fields where present

### Raw JSON

Raw JSON remains visible but secondary:

1. lower in the page than the reviewer summary
2. clearly labeled as source-of-truth payload
3. scrollable and easy to inspect

## Triage Ordering

Rows should no longer appear as a neutral flat list by default.

Default ordering should be:

1. rows with warnings first
2. unresolved `pending` rows before already-reviewed rows
3. then by frequency rank / display text

This matches the desired review behavior:

1. fast approvals for normal rows
2. deeper inspection only for higher-risk rows

## First Implementation Slice

The first implementation slice should stop before over-building:

1. backend-derived warnings for each row
2. backend-derived reviewer summary for each row
3. frontend queue sorting by risk + pending status
4. frontend summary cards above raw JSON

Not included in this slice:

1. keyboard shortcuts
2. tabbed review/raw modes
3. diff view
4. expanded QC heuristics beyond obvious derived warnings

## Testing

This slice needs:

1. backend tests for warning extraction and summary shaping
2. frontend tests for warning rendering and triage ordering
3. existing JSONL-only page flow must stay green

## Success Criteria

This slice is successful if:

1. reviewers can identify risky rows without reading raw JSON first
2. normal rows are easier to approve quickly
3. JSONL artifacts and decision sidecars remain the only review source of truth
4. no new database state is introduced
