# 2026-03-24 Learner Shell Refine Design

## Goal

Refine the learner-facing app shell so it matches the updated screenshot flow more closely: standalone search and settings tabs, cleaner word/phrase detail routes, accent-aware pronunciation display, a global + local translation toggle, denser knowledge-map range tiles, and a less cluttered detail experience focused on meanings rather than previous/next words.

## Current Problems

1. Search is embedded into both the knowledge map and the detail page, which makes those pages overloaded and does not match the screenshot flow.
2. Detail pages still live under `/knowledge/[entryType]/[entryId]`, even though they function as standalone entry pages rather than map-only subviews.
3. The detail page still shows previous/next word navigation, which is not part of the target interaction model.
4. The detail hero/card composition can overlap awkwardly, especially around the large picture area.
5. The knowledge-map bottom range strip uses large tiles and too few columns, making the page longer than necessary.
6. Translation visibility is not controllable as a global learner preference and cannot be quickly toggled in the detail surface.
7. Settings exists as a route but not as part of a persistent learner tab shell.

## Chosen Approach

Use a dedicated learner shell refactor:

- keep `/` as dashboard
- keep `/knowledge-map` and `/knowledge-list/[status]`
- add `/search` as a standalone learner tab
- keep `/settings` but move it into the same bottom-nav shell
- replace `/knowledge/[entryType]/[entryId]` with `/word/[id]` and `/phrase/[id]`

This approach keeps the existing learner API investment while correcting the navigation model and detail composition.

## Information Architecture

### Learner Routes

- `/`
  - dashboard home
- `/knowledge-map`
  - full mixed word+phrase map
- `/knowledge-list/[status]`
  - `new`, `learning`, `to_learn`, `known`
- `/search`
  - search history + live results
- `/settings`
  - learner settings
- `/word/[id]`
  - standalone word detail
- `/phrase/[id]`
  - standalone phrase detail

### Learner Bottom Nav

Persistent bottom tab bar across learner pages:

- `Home`
- `Knowledge`
- `Search`
- `Settings`

The learner detail routes should also keep this nav visible so detail remains part of the app shell rather than a disconnected subflow.

## Entry Detail Design

### Route Behavior

- All learner entry taps navigate to `/word/[id]` or `/phrase/[id]`.
- Search results navigate directly to those routes.
- `Discover`, `Learn`, list rows, map cards, tag view, and list view should all reuse the same route helper.

### Word Detail Content

Display:

- word
- part of speech
- accent-aware pronunciation
- browse rank
- CEFR level if present
- primary translation
- primary definition
- examples
- relation chips grouped from the existing relation payload
- confusable words if present

Recommended relation groups:

- synonyms
- antonyms
- related words

If relation types in data do not map cleanly to those groups, fall back to the raw relation type label rather than hiding data.

### Meaning Navigation

- remove previous/next entry navigation
- if a word has multiple meanings, use left/right controls for meanings only
- if a phrase has multiple senses, use the same pattern for senses
- single-meaning/single-sense entries should not render unnecessary navigation chrome

### Translation Toggle

Two layers:

1. Global setting
   - persisted in user preferences
   - controls whether translations show by default across learner surfaces
2. Local quick toggle in detail
   - toggles translation visibility for that page session
   - applies to definition translation and example translation together

Local state should initialize from the global preference.

### Hero/Card Layout

- keep the screenshot-style image-first hero
- move the content card fully below the hero image area so the picture no longer collides with the card body
- preserve the visual emphasis on the hero, but avoid floating overlap deep enough to obscure card copy

## Search Design

### Standalone Search Page

`/search` becomes the only learner search screen.

Behavior:

- initial state shows search history
- typing shows live search results
- tapping history or result opens `/word/[id]` or `/phrase/[id]`
- search history persists using the existing learner search-history API

### Removed Embedded Search

Remove search panels from:

- `/knowledge-map`
- `/word/[id]`
- `/phrase/[id]`

This keeps map/detail screens focused and matches the screenshot structure.

## Knowledge Map Density Change

The bottom mini-range strip should become a denser heatmap:

- around 20 columns on narrow mobile widths
- around 25 columns on wider mobile/tablet widths
- smaller square tiles
- same status color encoding

The goal is to shorten the vertical footprint of the strip while keeping the “whole range at a glance” function.

## Preferences / Backend Changes

### New Persisted Preference

Add a user preference for global translation visibility, for example:

- `show_translations_by_default: boolean`

Default:

- `true`

Reason:

- the app already depends heavily on translation support
- default-on is safer for existing behavior
- users can turn it off globally if they want a more immersion-first flow

### Existing Accent Preference

Accent-aware pronunciation selection already exists in the learner backend service. This slice should make the frontend consistently trust and display that returned pronunciation instead of using generic fallback copy when the API already resolved an accent-specific form.

### Learner Detail Payload Additions

Extend learner detail for word entries to expose:

- `confusable_words`
- enough relation metadata to render grouped chips/sections cleanly

No new search or map endpoints are required beyond this preference and detail enrichment.

## Testing Strategy

### Frontend

- dashboard route tests for updated navigation targets
- knowledge-map tests for denser strip and removed embedded search
- standalone search page tests
- settings tests for persisted global translation toggle
- word detail tests for:
  - meaning-only navigation
  - local translation toggle
  - relation/confusable rendering
  - no previous/next word controls
- route coverage for `/word/[id]` and `/phrase/[id]`

### Backend

- user-preferences API tests for the new translation-visibility field
- knowledge-map detail API tests for accent-aware pronunciation and confusable/relation payloads

### E2E

Update learner smoke to cover:

- bottom-nav `Search` and `Settings`
- admin/dev login unaffected
- learner search -> result -> detail
- fresh detail translation toggle behavior

## Risks

1. Route churn can break existing tests and links if route helpers are not centralized.
2. Relation labels may not be normalized enough for a perfect UI grouping on day one.
3. The current schema still has no real learner image asset, so the hero remains placeholder-based even after layout cleanup.

## Non-Goals

- real media/image asset pipeline
- changing learner status semantics
- redesigning admin routes
- persisting the local detail translation toggle separately from the global preference
