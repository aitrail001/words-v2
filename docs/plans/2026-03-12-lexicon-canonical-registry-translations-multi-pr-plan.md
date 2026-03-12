# 2026-03-12 — Lexicon canonical registry, form collapsing, and translations multi-PR plan

## Scope

Deliver the next lexicon-tool evolution as three focused PRs:

1. **PR 1 — canonical registry + deterministic form collapsing**
2. **PR 2 — learner-facing translations for `zh-Hans`, `es`, `ar`, `pt-BR`, `ja`**
3. **PR 3 — optional LLM adjudication for ambiguous surface-form canonicalization**

The goal is to stop treating every `wordfreq` surface form as an independent learner headword while keeping learner-important lexicalized forms such as `left`, `better`, and many uses of `given` as first-class entries.

## Agreed product decisions

1. Canonical identity must not live only in the learner-facing `words` table.
2. The system must be rebuildable from artifact files; production/preprod may keep persistent DB tables for fast lookup and incremental operations.
3. Deterministic rules should handle the large majority of morphological normalization.
4. LLM should enrich learner-facing content, not serve as the primary canonicalizer.
5. LLM adjudication is allowed only for the ambiguous tail and must choose among bounded candidate options.
6. Initial required learner-translation locales are `zh-Hans`, `es`, `ar`, `pt-BR`, and `ja`.
7. Lexicalized forms may be both:
   - linked as variants/forms of another canonical entry, and
   - preserved as their own learner-facing canonical entries.

## PR 1 — Canonical registry + deterministic form collapsing

### Goals

1. Introduce a canonical registry that answers:
   - has this surface form already been seen?
   - what canonical entry does it map to?
   - has it been generated/published?
2. Insert a deterministic canonicalization step before `build-base` / `wordfreq` rollout consumption.
3. Collapse obvious inflectional duplicates such as `thing/things` and `give/gives/giving`.
4. Preserve lexicalized forms such as `left` as separate canonical entries while linking them to related lemma families.

### Planned design

#### A. Artifact files

Add snapshot-side canonical outputs:

- `canonical_entries.jsonl`
- `canonical_variants.jsonl`
- `generation_status.jsonl`

Candidate fields:

- `canonical_entries.jsonl`
  - `entry_id`
  - `language`
  - `entry_type`
  - `canonical_form`
  - `display_form`
  - `normalized_form`
  - `status`
  - `is_learner_headword`
  - `first_seen_snapshot_id`
  - `last_generated_snapshot_id`
  - `last_published_source_reference`
  - `notes`

- `canonical_variants.jsonl`
  - `entry_id`
  - `surface_form`
  - `variant_type`
  - `canonical_form`
  - `decision`
  - `decision_reason`
  - `confidence`
  - `linked_entry_id`
  - `is_separately_learner_worthy`

- `generation_status.jsonl`
  - `entry_id`
  - `canonical_form`
  - `generated`
  - `compiled`
  - `published`
  - `last_snapshot_id`
  - `last_source_reference`
  - `updated_at`

#### B. DB tables

Add canonical lookup tables in backend/alembic:

- `lexicon_canonical_entries`
- `lexicon_canonical_variants`

Optional in PR 1 if it simplifies lookups:

- `lexicon_generation_status`

#### C. Tooling/CLI

Add canonical registry and lookup commands:

- `canonicalize-inventory`
- `lookup-entry --word <surface_or_lemma>`
- `status-entry --word <surface_or_lemma>`
- `sync-canonical-db --snapshot-dir ...`

#### D. Deterministic canonicalization logic

Candidate generation signals:

1. exact self candidate
2. WordNet `morphy` candidates by POS
3. suffix-based candidates for plural/3rd singular/past/participle/gerund/comparative/superlative patterns
4. curated irregular map for high-value cases (`went`, `gone`, `given`, `gave`, `better`, `best`, `worse`, `worst`, etc.)
5. wordfreq rank comparison between surface and candidate
6. WordNet lexicalization evidence / standalone-sense evidence

Decision outputs:

- `collapse_to_canonical`
- `keep_separate`
- `keep_both_linked`
- `unknown_needs_llm`

#### E. PR 1 acceptance examples

- `thing` + `things` => one canonical learner headword `thing`
- `give` + `gives` + `giving` => one canonical learner headword `give`
- `left` => its own canonical learner headword, linked to `leave`
- `given` => likely `keep_both_linked` depending on deterministic evidence

### Files likely touched

- `tools/lexicon/models.py`
- `tools/lexicon/build_base.py`
- `tools/lexicon/cli.py`
- `tools/lexicon/validate.py`
- `tools/lexicon/compile_export.py`
- new canonicalization helper(s) under `tools/lexicon/`
- `tools/lexicon/tests/test_build_base.py`
- new canonicalization tests under `tools/lexicon/tests/`
- backend model(s) under `backend/app/models/`
- new alembic migration under `backend/alembic/versions/`
- backend tests for canonical registry model/service/API if exposed immediately

## PR 2 — Learner-facing translations

### Goals

1. Extend lexicon enrichment to generate required learner translations for:
   - sense definition
   - example sentence(s)
   - short usage note
2. Validate required locales: `zh-Hans`, `es`, `ar`, `pt-BR`, `ja`
3. Import translation data into the local DB as far as the current schema safely supports.

### Planned design

1. Extend enrichment payload schema for per-sense translations.
2. Keep English as source; translations are learner-assist fields, not canonical identity fields.
3. Import meaning-level translations into the existing `translations` table.
4. If example-level translations do not fit the current schema cleanly, keep them in artifacts / staged JSON until a dedicated schema slice exists.

### Files likely touched

- `tools/lexicon/enrich.py`
- `tools/lexicon/validate.py`
- `tools/lexicon/models.py`
- `tools/lexicon/compile_export.py`
- `tools/lexicon/import_db.py`
- `backend/app/models/translation.py` or adjacent schema if expanded
- relevant tests/docs

## PR 3 — Optional ambiguous-form LLM adjudication

### Goals

1. Add an optional admin/operator step for ambiguous canonicalization outcomes.
2. Constrain the LLM to bounded deterministic candidate choices.
3. Keep this step optional and auditable.

### Planned design

1. Feed the LLM:
   - surface form
   - bounded canonical candidates
   - frequency + WordNet evidence summary
2. Permit only:
   - `collapse_to:<candidate>`
   - `keep_separate`
   - `keep_both_linked`
3. Persist decisions in artifact output and optionally sync to canonical DB.

### Files likely touched

- new adjudication module under `tools/lexicon/`
- `tools/lexicon/cli.py`
- `tools/lexicon/validate.py`
- tests/docs

## Verification strategy

### PR 1

- lexicon unit tests for canonicalization edge cases
- lexicon CLI tests for lookup/status commands
- import/registry tests for generated/published state
- targeted backend tests for new tables/models if applicable

### PR 2

- lexicon enrichment schema tests
- translation validation tests
- import tests for meaning-level translations

### PR 3

- bounded prompt/response parsing tests
- candidate-only adjudication tests
- no-invention safety tests

## Handoff and context-compaction resilience

To preserve continuity after compaction or session reset:

1. Keep this plan file updated with each PR.
2. Update `docs/status/project-status.md` after each PR lands, including exact evidence and the next PR milestone.
3. Use branch naming that encodes the sequence:
   - `feat_lexicon_canonical_registry_20260312`
   - `feat_lexicon_translations_20260312`
   - `feat_lexicon_ambiguous_form_adjudication_20260312`
4. When PR 1 closes, create a short follow-up plan doc or extend this one with:
   - what shipped
   - what remains for PR 2 and PR 3
   - any schema constraints discovered during implementation
5. Treat this plan doc + `docs/status/project-status.md` as the authoritative continuation context, rather than relying on chat-only memory.

## Current execution checkpoint

- **PR 1 branch:** `feat_lexicon_canonical_registry_20260312`
- **PR 1 status:** implementation + verification complete locally
- **Fresh evidence:** `152` lexicon tests passed and a real smoke snapshot confirmed `gives/giving -> give`, `things -> thing`, and `left` as `keep_both_linked` to `leave`
- **Next PR after merge:** PR 2 translations for `zh-Hans`, `es`, `ar`, `pt-BR`, and `ja`
- **Carry-forward files:** `tools/lexicon/models.py`, `tools/lexicon/build_base.py`, `tools/lexicon/canonical_forms.py`, `tools/lexicon/canonical_registry.py`, `tools/lexicon/cli.py`, `tools/lexicon/README.md`, `tools/lexicon/OPERATOR_GUIDE.md`, `docs/status/project-status.md`
