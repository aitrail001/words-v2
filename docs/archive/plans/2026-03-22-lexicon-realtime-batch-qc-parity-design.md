# Lexicon Realtime and Batch QC Parity Design

## Goal

Make realtime lexicon generation operationally equivalent to batch generation after a valid normalized artifact row exists, while preserving the current immediate realtime schema validation and without forcing realtime to emulate batch transport ledgers.

## Current state

The current lexicon pipeline has two different enforcement points:

- Realtime generation validates model output immediately in `tools/lexicon/enrich.py`.
- Batch generation records request/result lineage in `tools/lexicon/batch_prepare.py` and `tools/lexicon/batch_ingest.py`, then runs deterministic QC and review-queue generation in `tools/lexicon/qc.py`.

This means the transport layers are already different, but the post-generation review workflow can be unified.

Today the batch QC path is intentionally lightweight:

- accepted + valid rows become QC pass
- failed or invalid rows become QC fail
- only failed QC rows enter the review queue

The JSONL-only review UI already derives warning labels and review priority directly from compiled rows in `backend/app/services/lexicon_jsonl_reviews.py`. That is a second review-oriented heuristic layer, but it is not currently wired into the realtime generation path or the batch QC artifacts as a shared canonical service.

## Design decision

Do not make realtime generate synthetic batch request/result ledgers.

That would incorrectly couple realtime to batch-only concerns:

- `custom_id`
- shard file boundaries
- batch job upload/download metadata
- retry `attempt` lineage

Those are transport concerns, not review-quality concerns.

Instead, introduce a shared post-generation review-prep pipeline that both transport modes call after normalized rows exist.

## Recommended architecture

Split the overall workflow into two layers.

### 1. Generation layer

This remains transport-specific.

#### Realtime

- call the Responses-compatible endpoint directly
- validate the raw response immediately
- normalize it into the family-specific artifact row

#### Batch

- prepare and submit offline request rows
- ingest result rows
- normalize them into the same family-specific artifact row shape

### 2. Post-generation review-prep layer

This becomes shared.

Input:

- normalized artifact rows for `word`, `phrase`, or `reference`
- optional source metadata such as origin (`realtime` or `batch`) and transport lineage when available

Output:

- deterministic QC verdict rows
- warning labels
- review priority
- review queue rows
- review-facing metadata used by admin tooling

This shared layer becomes the operational equivalence point between realtime and batch.

## Boundary choice

The convergence point should be compiled or review-ready artifact rows, not raw model responses.

Why:

- the current admin review tooling already operates on compiled JSONL or review-staging rows derived from compiled JSONL
- `review_materialize` already assumes immutable compiled artifacts plus decision overlays
- the family contracts for `word`, `phrase`, and `reference` are already defined after normalization

Using compiled rows as the boundary avoids mixing:

- prompt construction
- transport retries
- gateway-specific response parsing
- batch file lineage

with the review-prep layer.

## Family scope

The shared layer should cover all currently supported families:

- `word`
- `phrase`
- `reference`

The family-specific schema validation remains where it already belongs:

- word enrichment validation in `tools/lexicon/enrich.py` and `tools/lexicon/schemas/word_enrichment_schema.py`
- phrase/reference row validation in the corresponding schema and compiled-record validators

The shared review-prep layer only consumes already-normalized rows.

## Proposed module shape

Add a new shared review-prep module under `tools/lexicon/`, for example `review_prep.py`.

Core responsibilities:

- compute deterministic QC verdict for a normalized row
- derive warning labels and review priority
- build review queue rows from verdict rows
- expose a single API used by both batch and realtime callers

Suggested public functions:

- `build_review_prep_rows(...)`
- `build_review_queue_rows(...)`
- `summarize_review_prep_rows(...)`

Suggested row responsibilities:

- family-agnostic common fields:
  - `entry_id`
  - `entry_type`
  - `normalized_form`
  - `review_priority`
  - `warning_labels`
  - `review_status`
- optional batch-only lineage:
  - `custom_id`
  - `attempt`
  - `status`
  - `validation_status`

The API should tolerate missing batch lineage so realtime can use it directly.

## Integration plan

### Batch integration

Replace or refactor `tools/lexicon/qc.py` so its current verdict and queue logic becomes a thin wrapper over the new shared review-prep module.

Batch-specific behavior that remains:

- loading `batch_results.jsonl`
- preserving `custom_id`
- applying manual overrides
- writing `batch_qc.jsonl`

### Realtime integration

After realtime enrichment has produced valid normalized rows and the artifact family output exists:

- run the shared review-prep layer against those rows
- emit the same review-prep artifacts batch users get
- surface the same warning labels and review queue behavior before human review

This should not replace the current realtime validation. It should follow it.

## Artifact expectations

Realtime should produce review-prep artifacts equivalent in meaning to the batch path, without pretending to be a batch request ledger.

Recommended artifacts for parity:

- `review_qc.jsonl` or a family-aware equivalent
- `review_queue.jsonl`
- review summary metadata if needed for admin ops

Batch can continue writing:

- `batch_qc.jsonl`
- `enrichment_review_queue.jsonl`

If naming is harmonized later, the implementation should still preserve backward compatibility for existing batch operators.

## Admin tool implications

The admin review surfaces should not need to care whether the artifact came from realtime or batch once review-prep has run.

That means:

- JSONL-only review can consume the same warning labels and review-priority metadata
- compiled review import can preserve the same metadata in staging rows
- `Lexicon Ops` can present a uniform review/readiness story

The current JSONL-only warning derivation in `backend/app/services/lexicon_jsonl_reviews.py` should either:

- be migrated to use the shared review-prep logic directly, or
- consume persisted review-prep artifacts instead of recomputing a divergent heuristic locally

The first option is preferred because it reduces drift.

## Error handling

### Realtime

- invalid raw model payloads still fail immediately
- only successfully normalized rows enter review-prep

### Batch

- transport failures and invalid ingested results still remain visible in batch ledgers
- the shared review-prep layer should treat these as review failures when normalized row data exists, or continue surfacing them as QC fail rows when only result metadata exists

### Mixed-family runs

- family-specific required fields remain validated before review-prep
- the shared layer must not weaken family-specific validation

## Testing strategy

Add parity tests at the normalized-row boundary.

Required coverage:

1. equivalent normalized `word` rows from realtime and batch produce the same warning labels, review priority, and queue behavior
2. equivalent normalized `phrase` rows do the same
3. equivalent normalized `reference` rows do the same
4. realtime still rejects invalid raw payloads before review-prep runs
5. batch ledger behavior remains unchanged for request/result lineage
6. admin review surfaces consume shared review metadata consistently

## Migration guidance

This should be done incrementally:

1. extract shared review-prep logic
2. refactor batch QC to use it
3. wire realtime artifact outputs into it
4. converge admin review metadata on the shared output

At no point should the batch transport model become a requirement for realtime.

## Non-goals

- replacing the existing realtime transport with batch
- inventing fake `custom_id` rows for realtime
- rewriting the compiled review system
- changing final `import-db` semantics
- collapsing review state storage modes into one system

## Recommendation

Implement operational equivalence after normalization, not before.

That preserves:

- realtime's immediate correctness gate
- batch's transport lineage and retry model
- one shared human-review preparation path across `word`, `phrase`, and `reference`

This is the smallest design that delivers the behavior you want without creating a transport-coupled architecture.
