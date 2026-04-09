# Learner Detail Schema Alignment Design

## Goal

Fix fresh-stack Docker bootstrap so local auth works without manual migration, and align learner settings/detail rendering with the real mixed lexicon schema for words and phrases.

## Problems To Solve

1. Fresh `docker compose up` on `main` starts the backend before schema migration, so `users` does not exist and `admin@admin.com` cannot log in until Alembic is run manually.
2. Learner translation settings expose incomplete language options and raw/partial labels instead of the actual supported locales in the schema.
3. Learner detail pages only partially respect translation settings and currently omit translated usage notes and translated examples even when the schema provides them.
4. Learner detail rendering does not faithfully follow the schema split between word-level fields and sense-level fields.
5. Important schema-backed learner fields such as inflections and forms are not shown.
6. Related words and other lexical references are not linked through to exact matching entries in the local DB.

## Recommended Approach

Extend the existing learner detail API/service contract rather than adding a separate detail backend. This keeps the frontend simple and lets the backend normalize word/phrase schema differences into one learner-facing shape.

## Backend Design

### Docker Bootstrap

- Add a one-shot `migrate` service to `docker-compose.yml`.
- Run `alembic upgrade head` in that service.
- Make `backend` and `worker` wait on successful migration completion.
- Keep `DEV_TEST_USERS_ENABLED=true`; once schema exists, the first request seeds `admin@admin.com` and `user@user.com` correctly.

### Supported Translation Locales

Treat the learner-supported locales as a fixed set derived from the schema and fixture data:

- `ar`
- `es`
- `ja`
- `pt-BR`
- `zh-Hans`

Expose full labels in the frontend while preserving locale codes in persisted preferences.

### Learner Detail Contract

Extend the knowledge-map learner detail payload so the frontend receives:

- entry-level fields:
  - `display_text`
  - `normalized_form`
  - `browse_rank`
  - `cefr_level`
  - `pronunciation`
  - `forms`
  - `confusable_words`
- per-sense/per-meaning fields:
  - `definition`
  - `part_of_speech`
  - `usage_note`
  - `register`
  - `primary_domain`
  - `secondary_domains`
  - `grammar_patterns`
  - `synonyms`
  - `antonyms`
  - `collocations`
  - examples with aligned localized example translations when available
  - localized definition and localized usage note for the selected locale
- exact-match link metadata for related strings that resolve to a known DB entry

### Exact-Match Linking

Resolve exact-match links server-side against existing words and phrases using normalized/display text equality only.

Linkable surfaces:

- synonyms
- antonyms
- collocations
- confusable words
- derivations
- example tokens/phrases when the exact string exists in the DB

No fuzzy matching in this slice.

## Frontend Design

### Settings

Update translation language options to show full names:

- Arabic
- Spanish
- Japanese
- Portuguese (Brazil)
- Chinese (Simplified)

Persist the same locale codes already stored in `UserPreference`.

### Word Detail

Render the learner detail page from the schema shape, not from simplified assumptions:

- pronunciation follows accent preference
- translation toggle controls:
  - translated definition
  - translated examples
  - translated usage note
- show forms block when populated:
  - `verb_forms`
  - `plural_forms`
  - `derivations`
  - `comparative`
  - `superlative`
- show compact metadata chips for:
  - part of speech
  - register
  - domain(s)
- show per-sense lexical sections:
  - synonyms
  - antonyms
  - collocations
  - grammar patterns
  - confusable words
- make exact-match related items clickable

### Phrase Detail

Phrase detail should use the same translated definition/example/usage-note behavior and exact-match linking for related fields, while only rendering fields that actually exist in phrase payloads.

## Suitable Additional Fields

High-value additions for this slice:

- `grammar_patterns`
- `antonyms`
- `register`
- `primary_domain`
- `secondary_domains`

Not recommended for learner detail in this slice:

- raw provenance
- model metadata
- operator/review metadata

## Testing Strategy

- backend:
  - migration bootstrap coverage for compose expectations where practical
  - learner detail API/service tests for locale selection, translated example alignment, usage-note translation, form fields, and exact-match linking
- frontend:
  - settings labels and persistence
  - learner detail translation toggle behavior
  - rendering of forms and sense-level lexical sections
  - clickable exact-match related links
- Docker/E2E:
  - fresh stack login without manual Alembic
  - detail page translation/settings smoke on real imported data
