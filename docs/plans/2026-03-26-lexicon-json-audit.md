# Lexicon JSON Audit

**Date:** 2026-03-26

## Scope

This audit covers the significant remaining JSON-heavy lexicon storage after the learner phrase contract/performance slice.

Disposition labels:

1. `keep_provenance`
2. `transitional_keep`
3. `normalize_now`
4. `normalize_later`

## Audit Table

| Area | File / Table / Column | Current Role | Risk | Disposition | Notes |
| --- | --- | --- | --- | --- | --- |
| Phrase provenance | `backend/app/models/phrase_entry.py` / `lexicon.phrase_entries.compiled_payload` | archival compiled learner payload used by review/admin/export compatibility | large payload but no longer primary learner read source | `keep_provenance` | keep as raw provenance and compatibility source only |
| Phrase seed provenance | `backend/app/models/phrase_entry.py` / `lexicon.phrase_entries.seed_metadata` | phrase-seed/operator provenance | low runtime risk | `keep_provenance` | useful for source tracing and inspector views |
| Word phonetics/forms | `backend/app/models/word.py` / `words.phonetics`, `words.word_forms` | structured learner/admin data | semantically structured, still JSON-backed | `normalize_later` | valuable but broader than a bounded follow-up slice |
| Word confusables | `backend/app/models/word.py` / `words.confusable_words` | learner/admin-rendered structured list | repeated rendering + import/export + validation drift risk | `normalize_now` | chosen cluster for this follow-up |
| Meaning metadata lists | `backend/app/models/meaning.py` / `secondary_domains`, `grammar_patterns` | learner-facing structured lists | already semantically stable, but not the biggest current risk | `normalize_later` | revisit with word-meaning schema cleanup if needed |
| Translation examples | `backend/app/models/translation.py` / `examples` | localized example list tied to one translation row | structured but compact | `normalize_later` | lower priority than word confusables |
| Enrichment raw outputs | `backend/app/models/lexicon_enrichment_run.py` / `generator_output`, `validator_output` | raw model I/O provenance | high value for audit/debug, bad normalization target | `keep_provenance` | keep raw |
| Review item compiled payload | `backend/app/models/lexicon_artifact_review_item.py` / `compiled_payload` | immutable review artifact payload | core review provenance | `keep_provenance` | keep raw |
| Review candidate metadata | `backend/app/models/lexicon_review_item.py` / `candidate_metadata`, selected synset id arrays | structured review staging payload | potentially normalizable, but bound to review workflow semantics | `transitional_keep` | revisit only with review workflow redesign |
| Review batch metadata | `backend/app/models/lexicon_review_batch.py` / `import_metadata` | operator/import summary blob | low value, low pressure | `transitional_keep` | may become typed later if queried more heavily |
| Lexicon jobs payloads | `backend/app/models/lexicon_job.py`, `lexicon_regeneration_request.py` | request/result payloads for durable jobs | provenance-first | `keep_provenance` | normalization would lose operator flexibility |
| Word list variation data | `backend/app/models/word_list_item.py` / `variation_data` | app-side list metadata | outside lexicon learner contract | `transitional_keep` | not part of this lexicon follow-up |

## Chosen Normalization Target

### `Word.confusable_words` -> `lexicon.word_confusables`

Reason:

1. semantically structured list with stable fields: `word`, `note`, `order_index`
2. already validated and rendered in learner/admin surfaces
3. imported/exported through lexicon tooling
4. small enough to normalize without reopening larger word-form or meaning-list schema work

## Result of This Follow-Up

1. add normalized child table `lexicon.word_confusables`
2. backfill existing `words.confusable_words` JSON into child rows
3. importer replaces normalized confusable child rows on reimport
4. learner/word API helpers prefer normalized rows, with JSON fallback retained during transition

## Deferred Next Candidates

1. `words.word_forms`
2. `meanings.secondary_domains`
3. `meanings.grammar_patterns`
4. `translations.examples`
