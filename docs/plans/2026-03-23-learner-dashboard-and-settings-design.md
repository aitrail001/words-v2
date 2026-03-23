# Learner Dashboard And Settings Design

**Date:** 2026-03-23
**Status:** Approved for implementation

## Goal

Refactor the learner-facing app shell so the root route becomes a mobile dashboard matching the new screenshots, while the full knowledge map moves to its own route and the learner gains filtered word-list and settings screens.

## Product Scope

The learner flow should support five primary surfaces:

1. `/` as the learner dashboard home
2. `/knowledge-map` as the full map view
3. `/knowledge-list/[status]` as filtered sortable entry lists
4. `/knowledge/[entryType]/[entryId]` as the entry detail view
5. `/settings` as learner preferences

The dashboard must expose the current counts and navigation points shown in the reference screenshots:

- tapping the uncovered total opens the full knowledge map
- tapping `New` opens the undecided list
- tapping `Started` opens the learning list
- tapping `To Learn` opens the to-learn list
- tapping `Discover` opens the full map focused on the learner's current discovery point
- tapping `Learn` opens the next learnable entry in browse-rank order

`Known` is also a first-class filtered list, even if it is not shown on the dashboard card.

## Recommended Architecture

Keep the existing mixed word+phrase learner model and persisted entry statuses, but split presentation responsibilities across dedicated routes:

- the current root page logic becomes a dedicated `knowledge-map` page component
- the new dashboard becomes a lightweight orchestration view that consumes summary/navigation API data
- filtered list pages use a dedicated list endpoint with status/search/sort support
- settings use the existing user-preferences API, extended only where persistence is genuinely needed now

This keeps the current map/detail work intact and avoids forcing one oversized page to behave as home, list, and map simultaneously.

## Navigation Model

### Dashboard

The dashboard is the new learner landing page.

It contains:

- top summary card with total uncovered count
- segmented progress bar with status distribution
- tappable status counts
- `Knowledge Map` section with `Discover` and `Learn` cards
- `Practice with Lexi` cards as presentational placeholders unless explicitly wired later

Navigation rules:

- total uncovered count -> `/knowledge-map`
- `New` -> `/knowledge-list/new`
- `Started` -> `/knowledge-list/learning`
- `To Learn` -> `/knowledge-list/to-learn`
- `Discover` -> `/knowledge-map?rangeStart=<current discovery range>`
- `Learn` -> `/knowledge/<entryType>/<entryId>` for the next learnable item

### Full Knowledge Map

The full-map route keeps the current screenshot-aligned map work:

- dense 100-entry range tiles
- cards/tags/list modes
- range drill-in
- search history and search results

The route should accept optional query parameters for:

- `rangeStart`
- `entryId`
- `entryType`
- optional `view`

That lets dashboard/list screens deep-link to the exact learner position.

### Filtered Lists

The list route is reusable for:

- `known`
- `new`
- `learning`
- `to-learn`

Mapping:

- `new` means persisted status `undecided`
- `to-learn` means persisted status `to_learn`

Each list page includes:

- search input
- sort menu
- vertically scrolling entry rows
- status control on each row
- tap-through to entry detail

Initial sort options should stay tight:

- rank ascending
- rank descending
- alphabetic ascending

## Backend/API Design

### Keep

- `GET /api/knowledge-map/overview`
- `GET /api/knowledge-map/ranges/{range_start}`
- `GET /api/knowledge-map/entries/{entry_type}/{entry_id}`
- `PUT /api/knowledge-map/entries/{entry_type}/{entry_id}/status`
- search/history endpoints
- `GET/PUT /api/user-preferences`

### Add

#### Dashboard summary endpoint

`GET /api/knowledge-map/dashboard`

Returns:

- `total_entries`
- counts for `undecided`, `to_learn`, `learning`, `known`
- `discovery_range_start`
- `discovery_range_end`
- `discovery_entry`
- `next_learn_entry`

Selection rules:

- `discovery_range_start` is the range containing the first entry whose status is not `known`
- `next_learn_entry` is the lowest-rank `to_learn` entry; if none exists, fallback to lowest-rank `learning`; if neither exists, fallback to the first non-known entry

#### Filtered list endpoint

`GET /api/knowledge-map/list`

Query params:

- `status`
- `q`
- `sort`
- `limit`

This endpoint returns mixed word+phrase summaries in the same learner shape already used by the map cards. The first implementation can keep pagination simple if needed, but it should at least support deterministic sorting and bounded result size.

## Settings Design

The screenshot shows more controls than the current backend supports. For this slice:

### Persist now

- preferred accent
- translation language
- knowledge-map view preference

### UI only for now

- daily goal
- reminders
- monthly report
- translate UI
- translate review cards
- sound effects
- hard word alert
- casing
- challenge types
- word examples
- video background
- clear cache

These can render as visual settings rows and toggles that are either disabled, local-only, or explicitly marked as not yet connected. The backend should not be widened just to fake persistence for options the app does not use yet.

## Error Handling

- if dashboard summary fails, show the shell with empty-state placeholders rather than crashing
- if the filtered list query fails, show retryable inline error copy
- if `next_learn_entry` is unavailable, disable the `Learn` CTA instead of sending the user nowhere
- if a route query points to a missing range or entry, fall back to the first valid learner range

## Testing Strategy

Frontend:

- dashboard route tests for count CTA navigation and card rendering
- full map route tests for preserved map behavior on `/knowledge-map`
- filtered list route tests for status mapping, sort UI, and item linking
- settings route tests for persisted settings wiring and screenshot markers

Backend:

- dashboard summary endpoint coverage
- filtered list endpoint coverage for status filtering, search, and sort

E2E:

- dashboard -> full map
- dashboard -> filtered lists
- dashboard `Discover` -> focused map
- dashboard `Learn` -> next learnable entry
- settings load/save for persisted fields

## Known Deliberate Gaps

- learner hero images remain placeholders until the schema gains real image assets
- `Practice with Lexi` cards are presentational in this slice
- many screenshot settings remain visual-only until product logic exists for them
