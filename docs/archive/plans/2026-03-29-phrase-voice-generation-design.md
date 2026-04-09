# Phrase Voice Generation Design

## Goal

Extend the existing voice generation pipeline so reviewed phrase datasets can be synthesized, imported, inspected, and played back with the same operational model as words, while improving `voice-generate` operator feedback so long runs expose meaningful live progress instead of going silent.

## Recommended Approach

Use the existing shared voice asset system rather than creating a phrase-only parallel stack.

- Keep one shared `lexicon_voice_assets` table.
- Reuse the existing three content scopes:
  - `word`: the spoken head item; for phrases this is the phrase text
  - `definition`
  - `example`
- Extend the asset ownership model to support phrase-side entities:
  - `phrase_entry_id`
  - `phrase_sense_id`
  - `phrase_sense_example_id`
- Keep storage policy behavior unchanged at the conceptual level:
  - `word_default`
  - `definition_default`
  - `example_default`
- Keep voice runs as CLI/output artifacts, separate from DB storage policies.

This is the smallest design that supports phrases without duplicating storage, playback, or admin logic.

## Why This Over Alternatives

### Option 1: Shared voice asset table with phrase ownership fields (recommended)

Pros:
- one playback route
- one storage policy model
- one admin UI surface
- one import/export mental model
- easy future support for mixed datasets

Cons:
- the asset table grows wider
- requires ownership validation to prevent mixed word/phrase references on a single asset

### Option 2: Separate phrase voice asset table

Pros:
- phrase schema is isolated
- fewer nullable foreign keys per table

Cons:
- duplicates importer, playback, inspector, and admin logic
- creates parallel policy handling for no real user benefit
- makes future cross-entry voice handling harder

### Option 3: Phrase-only offline artifacts with no DB integration

Pros:
- minimal first implementation

Cons:
- not usable by backend/admin in the same way as words
- becomes a dead-end operational path

## Data Model

### Voice assets

Extend `lexicon_voice_assets` so an asset can belong to either the word graph or the phrase graph.

Word-side ownership remains:
- `word_id`
- `meaning_id`
- `meaning_example_id`

Phrase-side ownership becomes:
- `phrase_entry_id`
- `phrase_sense_id`
- `phrase_sense_example_id`

Validation rules:
- each asset must belong to exactly one ownership path
- `content_scope=word` maps to `word_id` or `phrase_entry_id`
- `content_scope=definition` maps to `meaning_id` or `phrase_sense_id`
- `content_scope=example` maps to `meaning_example_id` or `phrase_sense_example_id`

### Storage policies

No new policy classes are needed. Phrases reuse the same three defaults:
- `word_default`
- `definition_default`
- `example_default`

That keeps the policy editor and playback resolution stable.

## Generator Behavior

`voice-generate` should support both:
- `entry_type: word`
- `entry_type: phrase`

Phrase planning rules:
- base unit text comes from the phrase head text
- definition units come from each phrase sense definition
- example units come from phrase sense examples
- locale and voice-role expansion remains the same as words
- voice profiles remain the same `word/definition/example` profile keys

The generator should not special-case phrase storage layout beyond deterministic IDs and relative paths that include entry type.

## Progress Output

`voice-generate` should emit structured operator feedback similar to the enrich tooling.

### Startup
- input path
- output dir
- provider/family
- locales
- concurrency
- resume/retry flags

### Planning summary
- rows scanned
- eligible words
- eligible phrases
- planned units by scope
- planned units by locale
- planned units by voice role

### Live progress
- generated count
- existing/skipped count
- failed count
- in-flight count
- throughput
- ETA when enough samples exist

### Error lines
For each failure, print a concise line including:
- unit id
- entry type
- display text
- locale
- voice role
- short error reason

### Completion summary
- planned/generated/existing/failed totals
- ledger paths
- next-step commands:
  - retry failed
  - import db

## Import Behavior

`voice-import-db` should resolve manifest rows against both entity graphs.

Word rows continue to resolve against:
- `Word`
- `Meaning`
- `MeaningExample`

Phrase rows resolve against:
- `PhraseEntry`
- `PhraseSense`
- `PhraseSenseExample`

Import should remain partial-success oriented:
- missing owner rows produce error reporting and skip that asset
- unrelated assets continue importing

## Backend/API/Admin Behavior

### Playback
Playback route behavior stays the same:
- `/api/words/voice-assets/{id}/content`

The route remains asset-centric, not entry-type-centric. Runtime resolution still uses:
- selected storage policy
- asset relative path

### Inspector/Admin
Add phrase voice assets to the inspector/admin surfaces where phrase detail already exists.

Recommended admin behavior:
- phrase detail shows `voice_assets` in the same style as word detail
- existing `/lexicon/voice` policy editor remains unchanged conceptually because policies are shared
- recent voice runs should continue showing run artifacts only, independent from DB policy state

## Testing Strategy

TDD-first implementation.

Required test layers:
- CLI unit tests for phrase planning and progress output
- DB import tests for phrase asset import
- backend API tests for phrase inspector/playback exposure
- admin frontend tests only where phrase voice data changes visible UI behavior

No implementation should start before failing tests exist for:
- phrase planning
- phrase import mapping
- phrase API exposure
- progress output lines

## Risks

Primary risks:
- mixed ownership ambiguity in `lexicon_voice_assets`
- phrase compiled rows may vary slightly from word rows in head-text fields
- progress logging can become noisy unless rate-limited and structured

Mitigations:
- add DB/model validation and focused tests around ownership rules
- normalize head text extraction into a single planner helper
- emit periodic progress snapshots instead of line-per-success spam
