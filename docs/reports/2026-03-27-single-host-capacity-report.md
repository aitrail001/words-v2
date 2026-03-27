# Single-Host Capacity Report

**Host budget under test:** 4 vCPU / 16 GB RAM
**Results directory:** `/Users/johnson/AI/src/words-v2/.worktrees/prod-benchmark-20260327/benchmarks/results/20260327-155539`

## Summary

- Highest tested stage meeting the initial p95/error bar: `1` VUs
- User-experience target used for the first pass: `p95 < 500ms` and `error rate < 5%` on the mixed API workload

## Stage Results

| VUs | RPS | p95 ms | p99 ms | Error rate | Backend max CPU % | Postgres max CPU % |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 4.80 | 254.41 | n/a | 0.0000 | 38.76 | 17.61 |
| 5 | 21.62 | 568.88 | n/a | 0.0030 | 99.99 | 20.31 |
| 10 | 28.75 | 1329.76 | n/a | 0.0030 | 106.41 | 46.88 |
| 25 | 42.26 | 2668.35 | n/a | 0.0091 | 105.25 | 60.85 |
| 50 | 48.64 | 4796.64 | n/a | 0.0208 | 113.21 | 24.47 |
| 100 | 56.24 | 7604.22 | n/a | 0.0193 | 114.33 | 26.94 |

## Interpretation

- This report is valid only for the production-like single-host Docker stack used in this run.
- It is not a universal production concurrency claim.
- If a later stage breaches the target, the prior passing stage is the initial safe tested envelope.

## Top SQL by Total Execution Time

| Calls | Total ms | Mean ms | Rows | Query |
|---:|---:|---:|---:|---|
| 9196 | 388.34 | 0.04 | 9196 | `SELECT users.id, users.email, users.password_hash, users.role, users.tier, users.is_active, users.created_at, users.updated_at FROM users WHERE users.id = $1::UUID` |
| 682 | 129.18 | 0.19 | 0 | `SELECT learning_queue_items.id, learning_queue_items.user_id, learning_queue_items.meaning_id, learning_queue_items.priority, learning_queue_items.review_count, learning_queue_item` |
| 1018 | 83.64 | 0.08 | 16288 | `SELECT lexicon.word_relations.id, lexicon.word_relations.word_id, lexicon.word_relations.meaning_id, lexicon.word_relations.relation_type, lexicon.word_relations.related_word, lexi` |
| 1205 | 77.20 | 0.06 | 4820 | `SELECT lexicon.meaning_examples.id, lexicon.meaning_examples.meaning_id, lexicon.meaning_examples.sentence, lexicon.meaning_examples.difficulty, lexicon.meaning_examples.order_inde` |
| 187 | 75.17 | 0.40 | 187 | `SELECT lexicon.phrase_entries.id, lexicon.phrase_entries.phrase_text, lexicon.phrase_entries.normalized_form, lexicon.phrase_entries.phrase_kind, lexicon.phrase_entries.language, l` |
| 1205 | 67.37 | 0.06 | 12050 | `SELECT lexicon.translations.id, lexicon.translations.meaning_id, lexicon.translations.language, lexicon.translations.translation, lexicon.translations.usage_note FROM lexicon.trans` |
| 1205 | 65.80 | 0.05 | 2410 | `SELECT lexicon.meanings.id, lexicon.meanings.word_id, lexicon.meanings.definition, lexicon.meanings.part_of_speech, lexicon.meanings.wn_synset_id, lexicon.meanings.primary_domain, ` |
| 1018 | 64.54 | 0.06 | 3054 | `SELECT lexicon.phrase_sense_example_localizations.id, lexicon.phrase_sense_example_localizations.phrase_sense_example_id, lexicon.phrase_sense_example_localizations.locale, lexicon` |
| 1205 | 55.60 | 0.05 | 8435 | `SELECT lexicon.meaning_metadata.meaning_id AS lexicon_meaning_metadata_meaning_id, lexicon.meaning_metadata.id AS lexicon_meaning_metadata_id, lexicon.meaning_metadata.metadata_kin` |
| 341 | 53.34 | 0.16 | 341 | `SELECT count(learning_queue_items.id) AS count_1 FROM learning_queue_items LEFT OUTER JOIN (SELECT review_history.meaning_id AS meaning_id, max(review_history.created_at) AS latest` |

## Top SQL by Mean Execution Time

| Calls | Total ms | Mean ms | Rows | Query |
|---:|---:|---:|---:|---|
| 187 | 75.17 | 0.40 | 187 | `SELECT lexicon.phrase_entries.id, lexicon.phrase_entries.phrase_text, lexicon.phrase_entries.normalized_form, lexicon.phrase_entries.phrase_kind, lexicon.phrase_entries.language, l` |
| 682 | 129.18 | 0.19 | 0 | `SELECT learning_queue_items.id, learning_queue_items.user_id, learning_queue_items.meaning_id, learning_queue_items.priority, learning_queue_items.review_count, learning_queue_item` |
| 341 | 53.34 | 0.16 | 341 | `SELECT count(learning_queue_items.id) AS count_1 FROM learning_queue_items LEFT OUTER JOIN (SELECT review_history.meaning_id AS meaning_id, max(review_history.created_at) AS latest` |
| 187 | 19.98 | 0.11 | 2992 | `SELECT lexicon.word_relations.id, lexicon.word_relations.word_id, lexicon.word_relations.meaning_id, lexicon.word_relations.relation_type, lexicon.word_relations.related_word, lexi` |
| 1018 | 83.64 | 0.08 | 16288 | `SELECT lexicon.word_relations.id, lexicon.word_relations.word_id, lexicon.word_relations.meaning_id, lexicon.word_relations.relation_type, lexicon.word_relations.related_word, lexi` |
| 1205 | 77.20 | 0.06 | 4820 | `SELECT lexicon.meaning_examples.id, lexicon.meaning_examples.meaning_id, lexicon.meaning_examples.sentence, lexicon.meaning_examples.difficulty, lexicon.meaning_examples.order_inde` |
| 1018 | 64.54 | 0.06 | 3054 | `SELECT lexicon.phrase_sense_example_localizations.id, lexicon.phrase_sense_example_localizations.phrase_sense_example_id, lexicon.phrase_sense_example_localizations.locale, lexicon` |
| 1205 | 67.37 | 0.06 | 12050 | `SELECT lexicon.translations.id, lexicon.translations.meaning_id, lexicon.translations.language, lexicon.translations.translation, lexicon.translations.usage_note FROM lexicon.trans` |
| 1205 | 65.80 | 0.05 | 2410 | `SELECT lexicon.meanings.id, lexicon.meanings.word_id, lexicon.meanings.definition, lexicon.meanings.part_of_speech, lexicon.meanings.wn_synset_id, lexicon.meanings.primary_domain, ` |
| 187 | 9.89 | 0.05 | 187 | `SELECT lexicon.lexicon_enrichment_runs.id, lexicon.lexicon_enrichment_runs.enrichment_job_id, lexicon.lexicon_enrichment_runs.generator_provider, lexicon.lexicon_enrichment_runs.ge` |
