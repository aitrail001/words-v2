# Word Enrichment Inspection API Design

## Goal

Add a narrow backend read API so admins/operators can inspect learner-facing enrichment that was imported into the local DB by the offline lexicon pipeline.

## Why this slice

The project can now:
- build WordNet/wordfreq-based snapshots
- enrich them offline
- import examples, relations, and enrichment provenance into the DB

But there is no backend read surface to inspect what the import produced without querying tables directly.

## Scope

Add one authenticated read endpoint:

- `GET /api/words/{word_id}/enrichment`

This endpoint should return:
- core word identity
- word-level phonetic provenance fields
- meanings
- meaning-linked examples
- meaning-linked relations
- referenced enrichment runs

## Why a separate endpoint

Do not expand the existing public word-detail contract yet.

A separate endpoint is better because:
- it avoids breaking or bloating the current learner-facing word detail response
- it is clearly an operator/admin inspection surface
- it keeps this slice read-only and low-risk

## Auth / security

Use the existing authenticated-user pattern (`get_current_user`) used across the repo.

Do not introduce a new admin-role guard in this slice because:
- the repo does not currently have a reusable admin-authorization dependency
- the immediate need is inspection in authenticated dev/admin contexts
- access hardening can be added later as a separate governance slice

## Response shape

Top-level:
- `id`
- `word`
- `language`
- `phonetic`
- `phonetic_source`
- `phonetic_confidence`
- `phonetic_enrichment_run_id`
- `meanings`
- `enrichment_runs`

Per meaning:
- `id`
- `definition`
- `part_of_speech`
- `example_sentence`
- `order_index`
- `examples`
- `relations`

Per example:
- `id`
- `sentence`
- `order_index`
- `source`
- `confidence`
- `enrichment_run_id`

Per relation:
- `id`
- `relation_type`
- `related_word`
- `related_word_id`
- `source`
- `confidence`
- `enrichment_run_id`

Per enrichment run:
- `id`
- `enrichment_job_id`
- `generator_provider`
- `generator_model`
- `validator_provider`
- `validator_model`
- `prompt_version`
- `prompt_hash`
- `verdict`
- `confidence`
- `token_input`
- `token_output`
- `estimated_cost`
- `created_at`

## Query strategy

Keep the implementation simple and explicit:
1. load the `Word`
2. load its `Meaning` rows ordered by `order_index`
3. load `MeaningExample` rows for those meanings ordered by `order_index`
4. load `WordRelation` rows for that word ordered by `relation_type`, `related_word`
5. collect referenced run IDs from:
   - `word.phonetic_enrichment_run_id`
   - `meaning_examples.enrichment_run_id`
   - `word_relations.enrichment_run_id`
6. load referenced `LexiconEnrichmentRun` rows

## Non-goals

This slice does not:
- add write/update review actions for enrichment data
- add filtering/pagination yet
- expose enrichment jobs directly as a separate resource
- merge enrichment fields into the main `/api/words/{word_id}` response
- enforce role-based admin authorization

## Success criteria

This slice is complete when:
1. authenticated users can inspect imported enrichment for a word
2. examples, relations, and referenced runs are returned together
3. 404 behavior matches existing word endpoints
4. focused backend tests pass
