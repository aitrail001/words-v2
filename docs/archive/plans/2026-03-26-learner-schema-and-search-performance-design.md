# Learner Schema and Search Performance Design

## Scope

This slice addresses three linked problems:
1. learner/word search paths still use scan-heavy text predicates that do not align with indexes
2. several learner-facing lexicon tables still keep duplicate legacy JSON columns after normalization
3. lexicon DB fixture artifacts under `tests/fixtures/lexicon-db` still underrepresent or omit aligned localized example translations, which weakens importer regression coverage

## Current findings

- Learner catalog search currently filters on `lower(display_text).contains(...)` / `lower(normalized_form).contains(...)` over a projected union catalog. On the live Docker DB this plan scans the full projected catalog (`12914` rows) and took about `67ms` in Postgres for one `bank` query.
- `/api/words/search` currently uses `Word.word.ilike(f"{q}%")`, which seq-scans `lexicon.words` on the live DB (`5473` rows).
- Equality lookup by `(word, language)` is already fast because `uq_word_language` is index-backed.
- Normalized child tables now exist for `word_forms`, `word_confusables`, `translation_examples`, and `meaning_metadata`, but the legacy JSON columns still exist on parent rows and are still written as transition fallback.
- Fixture artifacts in `tests/fixtures/lexicon-db/smoke/approved.jsonl` and `tests/fixtures/lexicon-db/full/approved.jsonl` contain many senses where English has multiple examples and localized `translations.<locale>.examples` does not align in count.

## Design decisions

### 1. Search/index hardening

- Add `pg_trgm` support and trigram GIN indexes for:
  - `lexicon.words.word`
  - `lexicon.phrase_entries.normalized_form`
  - `lexicon.phrase_entries.phrase_text`
- Keep exact lookup endpoints on existing equality indexes.
- Rework learner search so the DB filters base word and phrase tables before union/projection rather than filtering the full projected catalog with non-index-friendly predicates.
- Keep rank/order semantics stable for user-facing results.

### 2. Duplicate learner JSON retirement

- Treat the normalized child tables as canonical for these fields:
  - `words.word_forms`
  - `words.confusable_words`
  - `meanings.secondary_domains`
  - `meanings.grammar_patterns`
  - `translations.examples`
- Stop writing those legacy JSON columns in `import-db`.
- Remove read fallbacks for those fields from learner/words API shaping.
- Do not remove `words.phonetics` in this slice; it is a small fixed-shape blob and not the current bottleneck.
- Do not remove `phrase_entries.compiled_payload` in this slice; keep it as provenance/admin data, but avoid hot-path dependence on it.

### 3. Fixture/importer hardening

- Upgrade the lexicon DB fixture artifacts so at least the smoke fixture contains aligned localized example arrays for multiple examples.
- Add importer/tests that assert aligned two-example localized translations survive import and replacement semantics.
- Keep the contracts strict: `translations.<locale>.examples` must match the English example count.

## Expected outcome

- Search and learner list flows stop paying full-catalog scan cost for simple text queries.
- Parent lexicon rows become narrower because normalized child rows are the single learner-facing source for forms/confusables/meaning metadata/translation examples.
- Import/export fixtures and tests become trustworthy for multi-example localized translation preservation.
