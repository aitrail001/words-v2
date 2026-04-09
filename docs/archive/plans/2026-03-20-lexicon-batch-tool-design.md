# Lexicon Batch Enrichment Tool Design

## Purpose

This document defines the production design for the next-generation `tools/lexicon` admin pipeline in `words-v2`.

The target outcome is a durable, batch-first lexicon build system that can:

- enrich roughly **30,000 English headwords**
- enrich roughly **5,000 phrases / phrasal verbs / idioms**
- enrich a third lightweight dataset for **learner reference entries** such as:
  - common English given names
  - famous people
  - famous fictional characters
  - country / city / landmark / region names
  - demonyms and language names
  - honorifics / titles
  - common abbreviations learners frequently see or hear
- use OpenAI models cost-effectively for large offline runs
- validate outputs automatically against strict contracts
- support resumability, partial failures, out-of-order batch results, and deterministic re-runs
- support ongoing maintenance: re-enrichment, new entries, prompt upgrades, and schema evolution
- keep the current repo’s deterministic-first pipeline intact instead of replacing it

This document is written for Codex and senior engineers. It is intentionally prescriptive.

---

## Repository baseline

The current repository already has the foundations of an offline lexicon compiler:

- `build-base` creates normalized snapshot artifacts and canonical sidecars.
- `enrich` generates learner-facing enrichment payloads.
- `validate` checks snapshot and compiled outputs.
- `compile-export` produces publishable JSONL.
- `import-db` writes the compiled output into SQL tables.

Current artifacts and behaviors that must be preserved:

- snapshot-first workflow
- durable JSONL artifacts at each stage
- resumability and incremental writes
- deterministic canonicalization before LLM enrichment
- strict validation before DB import
- existing DB write path as the final publisher

The new design **adds** a Batch API execution backend, better schemas, and a lightweight learner-reference category. It does **not** replace the deterministic base-generation layer or the final compile/import path.

---

## Dataset families

The lexicon build system should treat the corpus as **three product families**, plus a seed-pack strategy.

### 1. Full lexical entries

These are normal words such as `take`, `appointment`, `tenant`, or `receipt`.

Characteristics:

- multi-sense allowed
- examples required
- collocations / grammar patterns useful
- learner metadata can be rich
- exported into word/meaning-related tables

### 2. Multiword expressions

These are phrases, phrasal verbs, idioms, and possibly collocations.

Characteristics:

- can be typed by phrase kind
- may need grammatical metadata such as separability or transitivity
- exported into phrase-related tables

### 3. Lightweight learner reference entries

These are **not** full dictionary entries. They are short-form learner support items whose value is mostly:

- pronunciation
- localized display form
- quick recognition
- a short explanation of who / what the thing is

Examples:

- `Charlotte` (common name)
- `Sherlock Holmes` (fictional character)
- `New Zealand` (country)
- `Melbourne` (city)
- `RSVP` (common abbreviation)
- `Dr.` / `Professor` / `sir` / `ma'am`

Characteristics:

- deliberately lightweight schema
- no sense explosion
- small number of fields
- usually one brief description
- not mixed into the main words or phrases schema

### 4. Curated learner-priority seed packs

Some items should remain part of the **main word corpus**, but should be explicitly prioritized because they are especially important for immigrants and foreign learners.

Examples:

- immigration / documents: visa, passport, application, appointment, resident
- work / admin: payslip, contract, supervisor, HR, deadline
- housing: landlord, tenant, lease, inspection, utility bill
- healthcare: clinic, prescription, referral, symptoms, appointment
- school / childcare: enrolment, permission slip, semester, homework
- transport / public life: station, platform, detour, parking permit, fare
- money / banking: invoice, receipt, direct debit, account number

These should **not** become a fourth schema family. They remain normal word entries, but operators should be able to feed curated seed lists into the inventory builder to guarantee coverage and early enrichment.

---

## Goals

### Primary goals

1. Generate high-quality learner-focused entries for words, phrases, phrasal verbs, idioms, and lightweight reference entries.
2. Optimize for **quality per dollar**, not raw cheapest output.
3. Treat the lexicon build as a **compiler pipeline**, not an ad hoc prompt script.
4. Make every run replayable, auditable, resumable, and diffable.
5. Make it safe to regenerate a subset without corrupting the corpus.
6. Provide deterministic quality gates before publication.
7. Let the system gradually expand into a broader learner-support corpus without redesigning the architecture each time.

### Secondary goals

1. Support future locale expansion.
2. Support UI-based review of flagged entries.
3. Support staged re-enrichment when prompt/schema quality improves.
4. Support curated seed packs for learner-priority domains.

### Non-goals

1. Real-time lookup generation for end users.
2. Replacing WordNet / `wordfreq` deterministic inputs with LLM-only generation.
3. Generating speech audio as part of the initial pipeline.
4. Building a full editorial CMS in the first milestone.
5. Building a full general knowledge entity database.

---

## Core design decisions

### 1. Keep JSONL as the canonical offline format

Use JSONL for all offline operational artifacts because it is:

- append-friendly
- shardable
- diffable in Git or artifact storage
- easy to replay
- easy to merge with out-of-order results

Compiled export remains JSONL. Optional Parquet exports can be added later for analytics, but **JSONL remains the source of truth** for the admin tool.

### 2. Add Batch API as a new execution backend

The current synchronous `enrich` mode remains for:

- smoke tests
- very small runs
- fixture generation
- repair/debugging

A new asynchronous **batch mode** is added for production bulk generation.

### 3. Preserve deterministic-first architecture

The model should enrich known normalized entries. The model should not decide the candidate inventory for the initial 30k corpus. Inventory building remains deterministic or operator-provided.

### 4. Separate generation, validation, QC, and publishing

Never collapse these concerns into one stage.

- generation produces raw structured candidate content
- validation checks contract correctness
- QC checks learner usefulness and editorial quality
- compile-export assembles publishable rows
- import-db is the only DB publisher

### 5. Make every unit of work addressable

Every request and every result must map to:

- entry id
- entry type
- prompt version
- schema version
- attempt number
- batch shard id

This is the core of safe retries and maintenance.

### 6. Treat reference entries as first-class, but lightweight

Names, place names, demonyms, titles, and common abbreviations are useful for learners, but they should not inherit the full complexity of the main word schema.

The system therefore adds a third family: `entry_kind = reference`.

### 7. Keep learner-priority domain terms inside the main word corpus

Terms such as `visa`, `lease`, `receipt`, and `referral` should not be moved into the lightweight reference dataset. They are better handled as normal words, with normal examples and collocations, but should be prioritized by seed curation.

---

## High-level architecture

```text
build-base / phrase-build-base / reference-build-base
    ↓
normalized snapshot JSONL
    ↓
batch-prepare
    ↓
batch input shards (.jsonl requests)
    ↓
batch-submit / batch-status
    ↓
batch-ingest
    ↓
validated enrichments + failures + ledgers
    ↓
batch-qc (optional separate batch pass)
    ↓
review queue / manual overrides
    ↓
compile-export
    ↓
compiled publishable JSONL
    ↓
validate --compiled-input
    ↓
import-db
```

Reference entries go through the same operational pipeline, but with a smaller schema and simpler QC rules.

---

## Module boundaries

Add or refactor the following modules under `tools/lexicon/`:

### 1. `contracts.py`
Shared canonical constants and dataclasses:

- schema versions
- prompt version ids
- entry kinds (`word`, `phrase`, `reference`)
- batch status enums
- retry strategies
- required locale sets
- relation type enums
- QC verdict enums
- reference type enums
- localization translation-mode enums

### 2. `schemas/`
JSON Schema definitions and normalization logic:

- `word_enrichment_schema.py`
- `phrase_enrichment_schema.py`
- `reference_entry_schema.py`
- `qc_verdict_schema.py`
- `compiled_export_schema.py`

### 3. `inventory.py`
Shared input builders and loaders:

- word inventory from existing snapshot
- phrase inventory from operator-provided seed files
- reference inventory from curated CSV/JSONL seed files
- filters for already-completed or already-published entries
- deterministic phrase normalization
- deterministic reference normalization

### 4. `batch_prepare.py`
Builds Batch API request files and sidecar ledgers.

Responsibilities:

- select pending entries
- choose prompt + schema + model
- assign `custom_id`
- shard requests by size and count
- write `batch_requests.jsonl`
- write `batch_input.<shard>.jsonl`

### 5. `batch_client.py`
Thin wrapper around the OpenAI Batch API.

Responsibilities:

- upload input file
- create batch
- fetch batch status
- fetch output file
- fetch error file

This module must remain easy to mock.

### 6. `batch_ledger.py`
Durable operational state.

Responsibilities:

- append-only write helpers
- idempotent record merge helpers
- summary views for CLI status
- per-entry completion resolution logic

### 7. `batch_ingest.py`
Reads output and error files, validates results, and writes normalized enrichment artifacts.

Responsibilities:

- map output line → request using `custom_id`
- extract structured JSON payload
- normalize and validate
- record failures and repair candidates
- update completion state

### 8. `qc.py`
Learner-quality review pass.

Responsibilities:

- deterministic heuristics
- optional LLM QC judge
- flag generation
- review queue generation

### 9. `overrides.py`
Human corrections and final patch layering.

Responsibilities:

- load `manual_overrides.jsonl`
- apply overrides during compile
- validate override schema
- preserve provenance

### 10. `phrase_pipeline.py`
Parallel support for phrase snapshots, enrichment, and export.

### 11. `reference_pipeline.py`
Parallel support for lightweight learner reference entries:

- seed loading
- normalization
- batch schema and prompt generation
- compile/export support
- import mapping

### 12. `reporting.py`
Run summaries for operators:

- pending / submitted / completed / failed counts
- batches by status
- cost estimates
- QC reject rates
- word / phrase / reference split

---

## New CLI surface

Add new commands without breaking existing commands.

### New commands

#### `batch-prepare`
Prepare batch request shards from an existing snapshot.

Example:
```bash
python -m tools.lexicon.cli batch-prepare   --snapshot-dir data/lexicon_snapshots/rollout-30000   --entry-kind word   --model gpt-5-mini   --prompt-version v2   --schema-version 2   --max-requests-per-shard 5000   --max-bytes-per-shard 150000000
```

Responsibilities:

- filter out already-finished entries
- filter out already-published entries unless `--rerun-existing`
- build request JSONL
- emit shard manifests and request ledgers

#### `batch-submit`
Upload prepared shard(s) and create batch jobs.

#### `batch-status`
Show status for one batch or all snapshot-associated batches.

#### `batch-ingest`
Download finished results and update enrichment artifacts plus ledgers.

#### `batch-retry`
Create retry shards from:

- schema failures
- transport failures
- QC rejections
- explicit operator requeue file

Modes:

- `repair`
- `regenerate`
- `escalate-model`

#### `batch-qc`
Run deterministic QC, optional LLM QC, and produce review queues.

#### `phrase-build-base`
Build or normalize the phrase seed snapshot.

#### `reference-build-base`
Build or normalize the lightweight reference seed snapshot.

Expected inputs:

- curated CSV or JSONL
- explicit `reference_type`
- optional per-row hints such as locale-specific display forms or seed descriptions

#### `review-export`
Export flagged entries for human review.

#### `review-apply`
Apply approved manual overrides and recompile.

### Existing commands that remain

These must keep working:

- `build-base`
- `enrich`
- `validate`
- `compile-export`
- `import-db`
- existing selection / review / status commands

---

## File and artifact contract

Each snapshot directory gains these additional artifacts.

### Generic snapshot files

```text
snapshot/
  canonical_entries.jsonl
  canonical_variants.jsonl
  generation_status.jsonl
  enrichments.jsonl
  enrich.checkpoint.jsonl
  enrich.decisions.jsonl
  enrich.failures.jsonl

  batch_jobs.jsonl
  batch_requests.jsonl
  batch_results.jsonl
  batch_qc.jsonl
  enrichment_review_queue.jsonl
  manual_overrides.jsonl

  batches/
    batch_input.00001.jsonl
    batch_input.00002.jsonl
    batch_output.00001.jsonl
    batch_error.00001.jsonl
    manifest.00001.json
```

### Additional inventory files by entry kind

#### Word snapshots

```text
snapshot/
  lexemes.jsonl
  senses.jsonl
```

#### Phrase snapshots

```text
snapshot/
  phrases.jsonl
```

#### Reference snapshots

```text
snapshot/
  references.jsonl
```

### Compiled outputs

Compiled export should produce separate publishable outputs by family:

```text
compiled/
  words.enriched.jsonl
  phrases.enriched.jsonl
  references.enriched.jsonl
```

### `batch_jobs.jsonl`
One line per submitted batch shard.

```json
{
  "batch_job_id": "uuid",
  "snapshot_id": "rollout-30000-v2",
  "shard_id": "00001",
  "entry_kind": "word",
  "model": "gpt-5-mini",
  "prompt_version": "v2",
  "schema_version": 2,
  "input_file_path": "batches/batch_input.00001.jsonl",
  "openai_batch_id": "batch_123",
  "openai_input_file_id": "file_123",
  "openai_output_file_id": null,
  "openai_error_file_id": null,
  "status": "submitted",
  "created_at": "ISO-8601",
  "submitted_at": "ISO-8601"
}
```

### `batch_requests.jsonl`
One line per request constructed.

```json
{
  "custom_id": "w:2ab1...:pv2:sv2:a1",
  "entry_id": "2ab1...",
  "entry_kind": "word",
  "surface_form": "take",
  "normalized_form": "take",
  "prompt_version": "v2",
  "schema_version": 2,
  "model": "gpt-5-mini",
  "attempt": 1,
  "shard_id": "00001",
  "request_hash": "sha256..."
}
```

### `batch_results.jsonl`
One line per ingested result.

```json
{
  "custom_id": "w:2ab1...:pv2:sv2:a1",
  "entry_id": "2ab1...",
  "status": "accepted",
  "validation_status": "valid",
  "qc_status": "pass",
  "attempt": 1,
  "model": "gpt-5-mini",
  "output_hash": "sha256...",
  "error_class": null,
  "error_detail": null,
  "ingested_at": "ISO-8601"
}
```

---

## `custom_id` strategy

`custom_id` must encode enough information to make retries and lineage trivial.

Recommended format:

```text
w:{entry_id}:pv{prompt_version}:sv{schema_version}:a{attempt}
p:{entry_id}:{phrase_type}:pv{prompt_version}:sv{schema_version}:a{attempt}
r:{entry_id}:{reference_type}:pv{prompt_version}:sv{schema_version}:a{attempt}
q:{entry_id}:pv{prompt_version}:sv{schema_version}:a{attempt}
```

Where:

- `w` = word enrichment
- `p` = phrase enrichment
- `r` = reference enrichment
- `q` = QC pass
- `entry_id` is the snapshot entry id
- `prompt_version` and `schema_version` make result provenance explicit
- `attempt` enables regeneration and escalation

Rules:

1. Never reuse a `custom_id`.
2. Never mutate the meaning of an existing `custom_id`.
3. Any retry gets a new `attempt` and therefore a new `custom_id`.

---

## Model strategy

### Recommendation

For the **runtime enrichment pipeline**, default to:

- primary generator: `gpt-5-mini`
- escalation / hard cases: `gpt-5.4`
- QC judge: `gpt-5-mini`
- final reviewer / high-risk QC rerun: `gpt-5.4`

### Compatibility note

Some Codex examples and internal setups may expose `gpt-5.4-mini` as a valid model string. The tool should therefore:

- default runtime generation to `gpt-5-mini`
- accept `gpt-5.4-mini` as a configured override if the operator environment supports it
- never hardcode model names in validation logic
- persist the actual model string used in run provenance

### Why this split

- batch generation is a large-volume, structured, repetitive workload
- the pipeline is contract-heavy and validation-heavy
- low-cost generation should be the default
- expensive model usage should be reserved for repair or difficult tails

### Reasoning effort defaults

For runtime API calls:

- generator: `low`
- repair: `medium`
- escalation: `medium` or `high`
- QC judge: `low`

The CLI should expose overrides.

---

## Schema design

### Design principles

1. Separate **headword metadata** from **sense metadata**.
2. Separate **English source content** from **localized learner content**.
3. Mark each field as:
   - deterministic
   - LLM-generated
   - operator-provided
4. Use tight cardinality bounds to control cost and UI sprawl.
5. Prefer explicit fields for app-critical behavior; use JSON only for flexible metadata.
6. Use the simplest viable schema for the reference family.

---

## Word schema improvements

The existing word enrichment schema is already strong. The following additions are recommended.

### Headword metadata

```json
{
  "headword": {
    "surface_form": "take",
    "normalized_form": "take",
    "pos": "verb",
    "ipa_us": "/teɪk/",
    "ipa_uk": "/teɪk/",
    "syllables": ["take"],
    "primary_stress_index": 0,
    "region_tags": ["global"],
    "common_in": ["spoken", "written"]
  }
}
```

Recommended additions:

- `ipa_us`
- `ipa_uk`
- `syllables`
- `primary_stress_index`
- `region_tags`
- `common_in`

### Sense-level additions

Recommended additions:

- `common_mistakes`
- `example_style`
- `example_is_generic`
- `safety_flags`
- `formality_notes`

Keep list-size limits tight:

- `examples`: max 3
- `synonyms`: max 5
- `antonyms`: max 5
- `collocations`: max 8
- `grammar_patterns`: max 6
- `common_mistakes`: max 3

### Important modeling recommendation

Translations for main word entries should be **run-configurable**, not universally required for every initial run. This allows:

1. English-only core generation
2. later locale backfill runs
3. targeted locale expansion for high-value subsets

---

## Phrase / idiom / phrasal verb schema improvements

Use a parallel phrase schema with shared learner metadata plus phrase-specific grammatical fields.

### Required phrase metadata

- `phrase_type`: `idiom`, `phrasal_verb`, `collocation`, optional future extensions
- `definition`
- `examples`
- `cefr_level`
- `register`
- `brief_usage_note`

### Phrasal-verb-specific fields

- `transitivity`: `transitive`, `intransitive`, `both`
- `separable`: `true`, `false`, `conditional`
- `object_placement_note`
- `literal_vs_idiomatic`

### Idiom-specific fields

- `typical_situations`
- `formality_notes`
- `common_variants`
- `meaning_is_literal` (usually false)

---

## Lightweight learner reference schema

This is the major new addition.

### Why this category exists

Many learners struggle with:

- saying names aloud
- recognizing exonyms and transliterations
- understanding who a famous person or fictional character is when referenced in media or conversation
- understanding place names used in news, forms, travel, or casual conversation
- understanding everyday abbreviations used in speech, email, forms, and signage

These items do not need the full complexity of dictionary-word enrichment. They need a compact learner support format.

### Recommended reference types

Initial enum set:

- `common_given_name`
- `famous_person`
- `fictional_character`
- `country`
- `city`
- `landmark`
- `region`
- `demonym`
- `language_name`
- `title_or_honorific`
- `common_abbreviation`
- `address_abbreviation`

### Canonical reference schema

```json
{
  "entry_id": "uuid",
  "entry_kind": "reference",
  "reference_type": "country",
  "surface_form": "Australia",
  "normalized_form": "australia",
  "schema_version": 1,
  "prompt_version": "v1",
  "headword": {
    "ipa_us": "/ɔˈstreɪliə/",
    "ipa_uk": "/ɒˈstreɪliə/",
    "syllables": ["Aus", "tra", "li", "a"],
    "primary_stress_index": 1,
    "region_tags": ["global"],
    "common_in": ["spoken", "written"]
  },
  "brief_description": "A country in the Southern Hemisphere and also a continent.",
  "learner_tip": "The stress is on STRAY.",
  "localizations": {
    "es": {
      "display_form": "Australia",
      "translation_mode": "unchanged",
      "brief_description": "País del hemisferio sur."
    }
  },
  "quality": {
    "generator_confidence": 0.95,
    "validation_status": "valid",
    "qc_status": "pass",
    "qc_score": 0.96
  }
}
```

### Required fields

- `entry_id`
- `entry_kind = reference`
- `reference_type`
- `surface_form`
- `normalized_form`
- `schema_version`
- `prompt_version`
- `headword.ipa_us`
- `headword.ipa_uk`
- `brief_description`
- `localizations`

### Optional but recommended fields

- `headword.syllables`
- `headword.primary_stress_index`
- `learner_tip`
- `region_tags`
- `common_in`
- `seed_metadata`

### Localization contract

For names and places, the output should **not** assume that “translation” means a literal translated word. Use this instead:

```json
{
  "display_form": "Londres",
  "translation_mode": "localized",
  "brief_description": "Capital city of the United Kingdom."
}
```

Allowed `translation_mode` values:

- `unchanged`
- `localized`
- `transliterated`

Examples:

- `Australia` → unchanged in many locales
- `London` → localized as `Londres` in Spanish
- some personal names → transliterated in some scripts

### Reference-family prompt design

Reference prompts should be smaller and cheaper than word prompts.

They should ask for:

- pronunciation fields
- a short description
- localizations with `display_form` and `brief_description`
- an optional learner tip

They should **not** ask for:

- multiple senses
- collocations
- grammar patterns
- multiple example sentences unless explicitly requested later

### Reference-family seed sourcing

These entries should come from **curated seed lists**, not LLM brainstorming.

Examples:

- `data/lexicon/reference_seeds/common_names.csv`
- `data/lexicon/reference_seeds/famous_people.csv`
- `data/lexicon/reference_seeds/fictional_characters.csv`
- `data/lexicon/reference_seeds/countries.csv`
- `data/lexicon/reference_seeds/cities.csv`
- `data/lexicon/reference_seeds/demonyms.csv`
- `data/lexicon/reference_seeds/abbreviations.csv`

### Notes on sensitive or variable fields

Avoid requiring a hard-coded gender label for personal names in the first milestone. If needed later, add an optional curated field such as `usage_note` or `name_context`, not a fragile LLM guess.

---

## Additional learner-support categories worth adding

Beyond names and place names, the following lightweight categories are high value for English learners:

### 1. Demonyms and language names

Examples:

- Australian
- Brazilian
- Arabic
- Spanish

Why valuable:

- common in news, forms, identity, and conversation
- often pronounced differently than learners expect

### 2. Titles and honorifics

Examples:

- Mr.
- Mrs.
- Ms.
- Dr.
- Prof.
- sir
- ma'am

Why valuable:

- high frequency in speech, email, forms, and workplace communication

### 3. Common abbreviations and acronyms

Examples:

- ASAP
- FYI
- RSVP
- ETA
- FAQ
- ID
- DOB
- PTO
- HR

Why valuable:

- learners often see these in forms, messages, and workplaces
- they usually need recognition plus a plain-English explanation, not a full dictionary entry

### 4. Address and navigation abbreviations

Examples:

- St.
- Rd.
- Ave.
- Blvd.
- Apt.
- Unit
- PO Box

Why valuable:

- common in addresses, delivery forms, and transport directions

### 5. Curated survival-English topical packs

These should stay in the main word dataset, but the design should support explicit seed packs for:

- immigration / public services
- healthcare
- housing
- education / childcare
- work / HR / payroll
- transport / navigation
- money / banking / billing

---

## Validation layers

### Layer 1 — Structured output contract

Use strict structured outputs for generation and QC.

### Layer 2 — Schema validation

Validate every ingested payload against the current schema version.

### Layer 3 — Structural invariants

Examples:

- locale blocks exist for configured required locales
- list bounds are enforced
- confidence fields are numeric and bounded
- `translation_mode` is valid for reference localizations
- required pronunciation fields exist for reference entries

### Layer 4 — Lightweight heuristics

Word and phrase examples:

- example count matches localized example count
- examples are not duplicates
- examples are not overloaded with proper nouns

Reference examples:

- brief description length is bounded
- learner tip is short and non-redundant
- no multi-sense payload sneaks into the reference schema
- display form is non-empty for each required locale

### Layer 5 — LLM QC

Optional second-pass QC returns a small verdict object:

- `accept`
- `needs_edit`
- `regenerate`

This should work for all three families, with family-specific heuristics.

---

## Compile/export contract

Compile step should:

- resolve latest accepted attempt per entry
- layer manual overrides on top
- emit separate outputs for words, phrases, and references
- produce deterministic publishable rows

Reference export should remain intentionally simple:

- one entry per row
- no sense join explosion
- nested localizations allowed in JSONL if preferred

---

## Recommended DB schema improvements

### Existing families

Keep current word / meaning / translation / phrase tables, but add room for:

- IPA split (`ipa_us`, `ipa_uk`)
- learner metadata
- richer example metadata
- version provenance

### New table: `reference_entries`

Core fields:

- `id`
- `reference_type`
- `surface_form`
- `normalized_form`
- `ipa_us`
- `ipa_uk`
- `syllables` JSONB
- `primary_stress_index`
- `brief_description`
- `learner_tip`
- `region_tags` JSONB
- `common_in` JSONB
- `schema_version`
- `current_prompt_version`
- `current_source_run_id`
- timestamps

### New table: `reference_localizations`

Core fields:

- `id`
- `reference_entry_id`
- `language`
- `display_form`
- `translation_mode`
- `brief_description`
- timestamps

### Optional future table: `reference_aliases`

Only if later needed for alternate spellings or exonyms.

### Optional topic-tag support for the main word corpus

If the product later wants stronger support for survival-English curation, add:

- `word_topics`
- `phrase_topics`

This is not required for the first milestone.

---

## Maintenance and update strategy

### Prompt versioning

Every generation request must persist:

- prompt version
- schema version
- model string
- reasoning effort

### Schema versioning

- schemas must be explicit and versioned
- compile/export must know how to read older accepted attempts where feasible
- breaking schema changes should trigger targeted re-enrichment, not forced full corpus rebuilds

### Re-enrichment modes

Support:

- add missing entries
- regenerate failed entries
- rerun entries with a new prompt version
- rerun entries for new locales only
- rerun only reference entries or only phrase entries

### Out-of-order and partial completion

Completion state is derived from ledgers and accepted artifacts, never from response order.

### Manual overrides

Manual corrections must be layered as explicit patch files, not by editing raw generated history in place.

---

## Operator workflow

### Main words

```text
build-base
→ batch-prepare --entry-kind word
→ batch-submit
→ batch-ingest
→ batch-qc
→ review-apply
→ compile-export
→ validate --compiled-input
→ import-db
```

### Phrases / idioms / phrasal verbs

```text
phrase-build-base
→ batch-prepare --entry-kind phrase
→ batch-submit
→ batch-ingest
→ batch-qc
→ review-apply
→ compile-export
→ validate --compiled-input
→ import-db
```

### Reference entries

```text
reference-build-base
→ batch-prepare --entry-kind reference
→ batch-submit
→ batch-ingest
→ batch-qc
→ review-apply
→ compile-export --include references
→ validate --compiled-input
→ import-db
```

---

## Definition of done for the implementation

The implementation is complete only when:

- words, phrases, and reference entries are all supported end-to-end
- batch request generation is deterministic
- out-of-order batch ingestion is proven in tests
- retries and escalations are proven in tests
- QC and manual overrides are proven in tests
- compiled outputs are valid for all supported entry families
- DB import remains the only publisher
- the operator workflow is documented
