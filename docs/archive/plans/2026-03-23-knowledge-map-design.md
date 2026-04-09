# Knowledge Map Design

**Date:** 2026-03-23  
**Status:** Approved for implementation  
**Live Status Board:** `docs/status/project-status.md`

---

## Goal

Add a learner-facing knowledge map that mixes words and phrases into one browseable catalog, persists per-user entry-level learning status, supports tile/range drill-in, and provides a richer learner detail/search flow than the current home search page.

---

## Product Scope

This slice adds:

- a mixed learner catalog over `word` and `phrase` entries
- persisted learner entry status with `undecided`, `to_learn`, `learning`, and `known`
- persisted learner preferences for pronunciation accent, translation locale, and default range view
- persisted learner search history
- a learner home flow that starts with a map of 100-entry ranges and drills into cards, tags, and list views
- a learner detail screen for both words and phrases

This slice does not add:

- per-sense learner status
- reference-entry browsing in the learner app
- generated media or real image assets
- SM-2 changes; review cards remain meaning-level and separate from entry-level browse status

---

## Core Decisions

### Entry-Level Status

Status is stored per learner and per entry, not per meaning/sense. This keeps the top-level map understandable and matches the reference UI where the learner quickly marks an item as already known or worth learning.

### Mixed Catalog

The learner catalog will combine:

- `Word`
- `PhraseEntry`

`ReferenceEntry` stays out of the learner map for now because it behaves more like localization/supporting metadata than learner-study content.

### Deterministic Shared Ordering

Words already have `frequency_rank`. Phrases do not. To let both content families live in one map, the learner browse layer will compute a shared `browse_rank`:

- words use `frequency_rank` when present
- phrases use a derived `browse_rank` that sorts after ranked words and remains stable

The first implementation uses a deterministic phrase ordering derived from phrase metadata and creation order so tiles stay stable without backfilling a new phrase corpus ranking pipeline.

### Placeholder Hero Media

The current schema has no reliable learner image asset field. The detail/card layout will therefore use a deliberate placeholder hero treatment:

- gradient/illustration-style block
- family/status/rank metadata overlay
- no fake asset API

This keeps the UI aligned with the reference structure without inventing unsupported media storage.

---

## Data Model Changes

### Learner Entry Status

Add a new persisted table keyed by user and learner entry identity:

- `user_id`
- `entry_type` (`word` or `phrase`)
- `entry_id`
- `status` (`undecided`, `to_learn`, `learning`, `known`)
- `updated_at`
- `created_at`

Unique constraint:

- `user_id + entry_type + entry_id`

### Learner Preferences

Add a small per-user preferences table:

- `user_id`
- `accent_preference` (`us`, `uk`, `au`)
- `translation_locale` (initially free string like `zh-Hans`, `es`, `ja`)
- `knowledge_view_preference` (`cards`, `tags`, `list`)
- timestamps

### Learner Search History

Add a persisted search history table:

- `user_id`
- `query`
- optional `entry_type`
- optional `entry_id`
- `last_searched_at`
- timestamps

History is de-duplicated by `user_id + query`.

---

## API Design

All learner endpoints sit behind authenticated learner access.

### `GET /api/knowledge-map/overview`

Returns the learner’s aggregate map broken into 100-entry buckets. Each bucket contains:

- `range_start`
- `range_end`
- `total_entries`
- counts by status
- percentages by status

### `GET /api/knowledge-map/ranges/{range_start}`

Returns the entries in a selected 100-entry bucket:

- mixed word/phrase items
- `browse_rank`
- learner status
- learner-facing summary fields
- adjacent range metadata for next/previous navigation

### `GET /api/knowledge-map/entries/{entry_type}/{entry_id}`

Returns the learner detail payload for one word or phrase:

- identity and learner status
- rank metadata
- display pronunciation chosen from learner accent preference when available
- translation chosen from learner translation locale when available
- full meanings/senses and examples
- previous/next entry metadata within the current range when available

### `PUT /api/knowledge-map/entries/{entry_type}/{entry_id}/status`

Upserts learner status for the selected entry.

### `GET /api/knowledge-map/search?q=...`

Searches mixed learner entries and returns rank/status-aware learner cards.

### `GET /api/knowledge-map/search-history`

Returns recent learner searches.

### `POST /api/knowledge-map/search-history`

Records or refreshes a search-history item when the learner searches or opens an item from search.

### `GET /api/user-preferences`

Returns learner preferences with defaults when the user has no row yet.

### `PUT /api/user-preferences`

Upserts learner preferences.

---

## Learner Payload Shape

The learner-facing contract should normalize words and phrases into one entry shell:

- `entry_type`
- `entry_id`
- `display_text`
- `normalized_form`
- `browse_rank`
- `status`
- `cefr_level`
- `pronunciation`
- `translation`
- `primary_definition`
- `part_of_speech` or `phrase_kind`

The detail view expands by family:

- words expose meanings, examples, relations, translations, phonetics
- phrases expose compiled senses and localized translations from `compiled_payload`

---

## Frontend Flow

### Home Knowledge Map

Replace the current basic dashboard with:

- a summary header
- a dense 100-entry map grid
- each tile showing status distribution as segmented color fill
- status legend
- quick access to recent search history

### Range Drill-In

Opening a tile shows one selected range with three view modes:

- `cards`
- `tags`
- `list`

#### Cards View

Shows a horizontally browsable learner card:

- placeholder hero
- entry text
- pronunciation based on accent preference
- rank
- primary translation from preferred locale
- primary definition
- actions:
  - `Should Learn`
  - `Already Know`
  - `Learning`
  - `Known`
  - `Learn more`

For `undecided` entries, the first emphasis is on `Should Learn` and `Already Know`.

#### Tags View

Compact grid of small clickable tiles with status color.

#### List View

Scrollable rows with brief summary, translation, and inline status control.

### Learner Detail

Clicking an entry opens a dedicated learner detail screen with:

- hero header
- entry title, pronunciation, status, rank
- horizontally swipeable meaning/sense panels
- examples under each panel
- translations localized to learner preference
- range-based previous/next controls
- search surface with recent history and live results

---

## Status Semantics

- `undecided`: learner has not classified the entry yet
- `to_learn`: learner marked it as worth learning but has not started
- `learning`: learner is actively learning it
- `known`: learner already knows it

Color mapping will be consistent across overview, range drill-in, and detail actions.

---

## Backend Notes

- Reuse existing word and phrase models rather than introducing a second learner catalog table.
- Keep browse aggregation in a dedicated learner service so the admin inspector contract remains separate.
- Phrase detail extraction should reuse the parsing already present in `lexicon_inspector.py`, but expose it through a learner-safe contract.
- Search history writes should be idempotent and lightweight.

---

## Testing Strategy

### Backend

- model tests for new learner tables
- API tests for overview, range browse, detail, status update, preferences, and search history
- mixed word/phrase browse ordering coverage
- accent/translation preference selection coverage

### Frontend

- home knowledge map rendering
- range drill-in state transitions
- cards/tags/list switching
- detail panel rendering for words and phrases
- status updates and optimistic refresh
- search history and live search behavior

---

## Risks and Guardrails

- Phrase ranking is not corpus-backed yet, so ordering must be clearly deterministic and documented.
- Phrase compiled payloads may vary in completeness; learner UI must tolerate missing translations/examples.
- Entry-level status is intentionally simpler than sense-level knowledge and should not be over-interpreted by review logic.
