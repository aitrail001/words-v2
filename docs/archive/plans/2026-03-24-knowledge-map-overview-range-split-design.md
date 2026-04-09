# Knowledge Map Overview/Range Split Design

## Goal

Refocus `/knowledge-map` on the full knowledge-map overview only, and move all per-range detail interaction into a dedicated route at `/knowledge-map/range/[start]`.

## Why

The current `/knowledge-map` page tries to be both the global board and the selected-range detail view. That makes the page heavier than the product flow the user wants, and it mixes two different navigation intents:

- global browsing across all 100-entry buckets
- detailed browsing within a single 100-entry bucket

The desired behavior is:

- `/knowledge-map` shows only the full board of 100-entry tags
- clicking a range tag navigates to a dedicated range detail page
- the range detail page owns cards/tags/list views plus previous/next range navigation

## Recommended Approach

Use a route split:

- `/knowledge-map`
- `/knowledge-map/range/[start]`

This is better than query-string state because it produces cleaner deep links and clearer page responsibilities.

## Route Responsibilities

### `/knowledge-map`

This page becomes the full-board overview only.

It should show:

- page title and total entry count
- explanatory copy
- the dense grid of 100-entry range tiles

It should not show:

- selected-range label
- cards/tags/list view toggles
- selected-entry hero card
- mini strip for words inside a range

Interaction:

- clicking a tile navigates to `/knowledge-map/range/[range_start]`

### `/knowledge-map/range/[start]`

This page owns the current detailed experience for one range.

It should show:

- range label
- cards/tags/list toggles
- selected-entry card or tags/list presentation
- bottom mini strip for the entries inside the range
- left/right arrows to navigate to previous/next range routes

Interaction:

- bottom left/right range arrows navigate to previous/next range route if available
- bottom mini strip still selects an entry within the current range
- clicking a different overview tile is no longer possible from this route; that belongs to `/knowledge-map`

## Component Structure

Extract the current range-detail UI into a shared client component so the route split is clean.

Recommended shape:

- `frontend/src/components/knowledge-map-range-detail.tsx`
  - loads a range by `rangeStart`
  - owns selected entry state
  - owns cached entry detail state
  - owns cards/tags/list rendering
  - owns bottom mini strip
  - owns previous/next range route links

Then:

- `frontend/src/app/knowledge-map/page.tsx`
  - overview-only page
- `frontend/src/app/knowledge-map/range/[start]/page.tsx`
  - small wrapper that passes the route param into the shared detail component

## Data Flow

Overview page:

- fetch `getKnowledgeMapOverview()`
- render tiles
- each tile links to `/knowledge-map/range/[range_start]`

Range detail page:

- fetch `getUserPreferences()`
- fetch `getKnowledgeMapRange(rangeStart)`
- fetch entry detail lazily for the currently selected entry
- cache entry detail by `entry_type:entry_id`

No backend contract changes are required for this slice.

## Error Handling

Overview page:

- if overview fails, show an empty-state fallback instead of range detail chrome

Range detail page:

- invalid `start` route param should fail closed to a friendly empty state or `not found`
- missing range data should not render stale data from another range
- switching previous/next range should reset active entry index and meaning index

## Testing

Frontend tests should cover:

- `/knowledge-map` renders only overview content
- `/knowledge-map` links each range tile to `/knowledge-map/range/[start]`
- `/knowledge-map/range/[start]` loads the selected range detail
- previous/next range arrows on the range page navigate correctly
- card/detail sync regression still holds on the new range page

Live verification should cover:

- open `/knowledge-map`
- confirm only the full map board is visible
- click a range tile and land on `/knowledge-map/range/[start]`
- move between entries inside the current range
- move between previous/next ranges with the bottom arrows
