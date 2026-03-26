# Learner POS Normalization Design

## Goal

Normalize learner-facing word part-of-speech storage out of `lexicon.words.learner_part_of_speech` JSON into structured rows so learner/admin reads stop depending on JSON arrays for hot-path behavior.

## Architecture

Add a new child table `lexicon.word_part_of_speech` keyed by `word_id` and `order_index`. Importer and runtime reads will prefer the normalized rows, while the legacy JSON column remains as transitional storage for one rollout slice.

## Design

### 1. Canonical storage
- Create `lexicon.word_part_of_speech` with `id`, `word_id`, `value`, `order_index`.
- Backfill from existing `words.learner_part_of_speech` arrays.
- Keep `words.learner_part_of_speech` temporarily, but stop treating it as authoritative.

### 2. Read path
- Learner list/detail derives primary display POS from the first ordered normalized row.
- Admin/enrichment APIs can expose the ordered full POS list from normalized rows.
- Hot paths must explicitly eager-load `part_of_speech_entries`; no lazy-load serializer dependence.

### 3. Write path
- `tools/lexicon/import_db.py` replaces normalized POS rows from compiled `part_of_speech` arrays.
- Transitional JSON may remain on the model for compatibility, but importer logic should no longer rely on it for correctness.

### 4. Error handling
- Empty or missing POS arrays produce no normalized child rows.
- Runtime shaping returns `None` / `[]` rather than synthetic fallback text.

### 5. Testing
- Migration backfill test for existing JSON arrays.
- Importer replacement test for repeated imports.
- Learner/admin read tests proving normalized rows override stale JSON.

### 6. Scope
- In scope: schema, importer writes, runtime reads, tests, status update.
- Out of scope: dropping the legacy JSON column, changing phrase provenance storage, precomputed search projections.
