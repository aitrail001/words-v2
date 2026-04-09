# Lexicon Review Staging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add offline lexicon risk-scoring and review-preparation artifacts, define a future import path into staging review storage, and document the delayed admin UI integration.

**Architecture:** Keep the current lexicon pipeline offline-first. Add a deterministic risk-scoring step after `build-base`, optionally run bounded rerank only for risky lexemes, and write a new `selection_decisions.jsonl` artifact plus an optional `review_queue.jsonl`. Treat database-backed review and admin UI as a later staged integration, but define their contracts now so the tool output is stable.

**Tech Stack:** Python stdlib, existing `tools/lexicon` CLI/build-base/rerank modules, JSON/JSONL artifacts, future FastAPI/Postgres/admin integration.

---

## Scope Summary

This plan documents the exact review-prep contract for the lexicon tool.

### New offline artifact

Primary new file:

- `selection_decisions.jsonl`

Optional convenience artifact:

- `review_queue.jsonl`

### New logic to define

- exact risk-score formula
- exact rerank routing thresholds
- exact auto-accept rules
- exact future CLI surface
- exact future staging import shape

---

## Exact `selection_decisions.jsonl` Schema

One row per lexeme.

```json
{
  "schema_version": "lexicon_selection_decision.v1",
  "snapshot_id": "lexicon-20260308-benchmark-holdout-wordnet-wordfreq",
  "lexeme_id": "lx_bank",
  "lemma": "bank",
  "language": "en",
  "wordfreq_rank": 1234,
  "available_wordnet_sense_count": 18,
  "candidate_pool_count": 8,
  "deterministic_target_count": 6,
  "deterministic_selected_wn_synset_ids": [
    "bank.n.01",
    "bank.v.03",
    "bank.v.05",
    "depository_financial_institution.n.01",
    "bank.v.01",
    "bank.n.09"
  ],
  "selection_risk_score": 6,
  "selection_risk_reasons": [
    "available_senses>=12",
    "deterministic_target_count=6",
    "small_cutoff_margin",
    "specialized_or_institutional_candidates_near_cutoff"
  ],
  "risk_band": "rerank_and_review_candidate",
  "rerank_recommended": true,
  "rerank_candidate_source": "candidates",
  "rerank_candidate_limit": 8,
  "rerank_applied": true,
  "rerank_candidate_wn_synset_ids": [
    "bank.n.01",
    "bank.v.03",
    "bank.v.05",
    "depository_financial_institution.n.01",
    "bank.v.01",
    "bank.n.09",
    "bank.n.04",
    "bank.v.02"
  ],
  "reranked_selected_wn_synset_ids": [
    "depository_financial_institution.n.01",
    "bank.n.09",
    "bank.n.01",
    "bank.v.03",
    "bank.v.01",
    "bank.n.04"
  ],
  "replacement_count": 1,
  "auto_accept_eligible": true,
  "auto_accepted": true,
  "review_required": false,
  "review_reasons": [],
  "deterministic_vs_rerank_changed": true,
  "deterministic_vs_rerank_reordered_only": false,
  "candidate_metadata": [
    {
      "wn_synset_id": "bank.n.01",
      "part_of_speech": "noun",
      "canonical_label": "bank",
      "canonical_gloss": "sloping land beside a body of water",
      "lemma_count": 12,
      "query_lemma": "bank",
      "deterministic_score": 35.0,
      "deterministic_rank": 1,
      "deterministic_selected": true,
      "rerank_exposed": true,
      "rerank_selected": true,
      "candidate_flags": ["polysemy_boundary"]
    }
  ],
  "generated_at": "2026-03-08T00:34:04Z",
  "generation_run_id": "selection-review-2026-03-08T00:34:04Z"
}
```

### Field notes

- `candidate_metadata` intentionally preserves original candidate context so future DB/UI review does not need to reconstruct it from WordNet at read time.
- `deterministic_vs_rerank_reordered_only=true` only when the set is unchanged and order alone differs.
- `review_required=true` means it should appear in the future admin review queue by default.

---

## Exact Risk-Score Formula

Risk score is additive.

### Inputs

- `available_wordnet_sense_count`
- deterministic selected count (`4`, `6`, or `8`)
- deterministic cutoff margin
- candidate POS competition near cutoff
- candidate flags near selection boundary
- word frequency priority
- label-drift evidence

### Formula

```text
risk_score =
  sense_breadth_score
+ target_count_score
+ cutoff_margin_score
+ pos_competition_score
+ tail_risk_score
+ label_drift_score
+ frequency_priority_score
```

### Components

#### 1. Sense breadth score

- `+3` if `available_wordnet_sense_count >= 20`
- `+2` if `available_wordnet_sense_count >= 12 and < 20`
- `+1` if `available_wordnet_sense_count >= 8 and < 12`
- else `+0`

#### 2. Deterministic target-count score

- `+2` if deterministic selected count is `8`
- `+1` if deterministic selected count is `6`
- else `+0`

#### 3. Cutoff-margin score

Let `cutoff_margin = selected_last_score - next_excluded_score`.

- `+2` if `cutoff_margin <= 3.0`
- `+1` if `cutoff_margin <= 6.0`
- else `+0`

#### 4. POS-competition score

Evaluate candidates within the top `target_count + 2` region.

- `+2` if at least `2` POS groups have candidates within `3.0` score points of the cutoff
- `+1` if at least `2` POS groups have candidates within `6.0` score points of the cutoff
- else `+0`

#### 5. Tail-risk score

Evaluate candidate flags in the top `target_count + 2` region.

Add `+1` for each present class, capped at `+2` total:

- sports
- legal/institutional
- religious/biblical
- geometry/technical
- highly abstract tail
- event/geographic tail

#### 6. Label-drift score

- `+1` if an alias-like or low-affinity candidate appears within the top `target_count + 2`
- else `+0`

#### 7. Frequency-priority score

- `+1` if `wordfreq_rank <= 10000`
- else `+0`

### Routing bands

- `0-2` → `deterministic_only`
- `3-5` → `rerank_recommended`
- `6+` → `rerank_and_review_candidate`

---

## Exact Auto-Accept Rules

If rerank is applied, auto-accept when all rules pass.

### Hard requirements

- rerank output is fully grounded
- selected count is valid
- no duplicate synsets
- no invented IDs

### Stability requirements

- if target count is `4`, `replacement_count <= 2`
- if target count is `6` or `8`, `replacement_count <= 3`
- no new suspicious label-drift candidate introduced
- rerank does not increase suspicious tail flags compared with deterministic selection
- rerank does not collapse POS diversity in an obviously harmful way for a broad everyday lemma

### Review-required triggers

Set `review_required=true` if any of these are true:

- replacement count exceeds auto-accept threshold
- rerank introduces label-drift candidates
- rerank introduces more specialized/institutional/religious/geometry tails than deterministic selection
- a very high-frequency word (`wordfreq_rank <= 3000`) changed substantially
- deterministic and rerank disagree on more than half of the selected senses
- lexeme is tagged as protected/high-value editorial inventory in a future override list

---

## Future CLI Additions

### 1. `score-selection-risk`

Purpose:
- read a snapshot
- compute candidate metadata, deterministic margins, flags, and risk score
- write `selection_decisions.jsonl`

Example:

```bash
python3 -m tools.lexicon.cli score-selection-risk \
  --snapshot-dir data/lexicon/snapshots/demo \
  --output data/lexicon/snapshots/demo/selection_decisions.jsonl
```

### 2. `prepare-review`

Purpose:
- read snapshot + `selection_decisions.jsonl`
- run bounded `candidates` rerank only for lexemes in risk bands `rerank_recommended` or `rerank_and_review_candidate`
- apply auto-accept rules
- rewrite `selection_decisions.jsonl`
- optionally emit `review_queue.jsonl`

Example:

```bash
python3 -m tools.lexicon.cli prepare-review \
  --snapshot-dir data/lexicon/snapshots/demo \
  --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl \
  --provider-mode auto \
  --candidate-limit 8 \
  --review-queue-output data/lexicon/snapshots/demo/review_queue.jsonl
```

### 3. `import-review-batch` (future backend-integrated admin command)

Purpose:
- load `selection_decisions.jsonl` + snapshot artifacts into staging review tables
- create one `LexiconReviewBatch`

Example:

```bash
python3 -m tools.lexicon.cli import-review-batch \
  --snapshot-dir data/lexicon/snapshots/demo \
  --decisions data/lexicon/snapshots/demo/selection_decisions.jsonl \
  --source-reference demo-20260308
```

### 4. `publish-review-batch` (future)

Purpose:
- publish approved staged selections into learner-facing DB tables

This should remain separate from import.

---

## Files To Add In The Tool

### Offline tool files

- Create: `tools/lexicon/selection_review.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/build_base.py` only if extra candidate metadata hooks are needed
- Modify: `tools/lexicon/rerank.py` only if the review-prep step needs shared helper functions
- Create: `tools/lexicon/tests/test_selection_review.py`
- Update: `tools/lexicon/README.md`
- Update: `tools/lexicon/OPERATOR_GUIDE.md`

### Future backend files

These are TODO for a later slice and should not be implemented in the current lexicon-only phase:

- Create: `backend/app/models/lexicon_review.py`
- Create: `backend/alembic/versions/<new_revision>_add_lexicon_review_staging.py`
- Create: `backend/app/api/admin_lexicon_review.py`
- Create: `backend/tests/test_admin_lexicon_review.py`

Suggested backend pattern references for that future slice:

- `backend/app/models/import_job.py`
- `backend/app/api/import_jobs.py`
- `backend/app/api/word_lists.py`
- `backend/app/main.py`
- `backend/app/models/word.py`
- `backend/app/models/meaning.py`
- `backend/alembic/versions/006_add_lexicon_import_provenance.py`

### Future admin frontend files

Deferred until an admin app exists in this rebuild:

- `admin-frontend/...` review queue page
- `admin-frontend/...` batch detail page
- `admin-frontend/...` lexeme review detail page
- `admin-frontend/...` diff and comments components

---

## Task Breakdown

### Task 1: Add offline risk-scoring artifact

**Files:**
- Create: `tools/lexicon/selection_review.py`
- Modify: `tools/lexicon/cli.py`
- Create: `tools/lexicon/tests/test_selection_review.py`

**Step 1: Write failing tests**
- load snapshot candidates and compute `selection_risk_score`
- verify risk bands and reasons
- verify `selection_decisions.jsonl` output schema

**Step 2: Verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_selection_review`
Expected: fail before implementation.

**Step 3: Implement minimal scoring path**
- read snapshot
- reconstruct ranked candidate metadata
- compute risk score, reasons, and routing band
- write `selection_decisions.jsonl`

**Step 4: Verify GREEN**
Run: `python3 -m unittest tools.lexicon.tests.test_selection_review`
Expected: pass.

### Task 2: Add rerank preparation step

**Files:**
- Modify: `tools/lexicon/selection_review.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_selection_review.py`

**Step 1: Write failing tests**
- rerank only risky lexemes
- apply auto-accept rules
- emit `review_queue.jsonl` for `review_required=true` lexemes

**Step 2: Verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_selection_review`
Expected: fail before implementation.

**Step 3: Implement minimal review-prep flow**
- call bounded `candidates` rerank only when recommended
- compare deterministic vs rerank sets
- apply auto-accept and review-required rules
- update decision rows and optional queue output

**Step 4: Verify GREEN**
Run: `python3 -m unittest tools.lexicon.tests.test_selection_review`
Expected: pass.

### Task 3: Document and validate offline review-prep flow

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Document commands and artifact semantics**
- add `score-selection-risk` and `prepare-review`
- explain risk bands and auto-accept behavior
- mark admin UI and DB-backed review as TODO/future integration

**Step 2: Verify docs consistency**
- check command examples and file names match implementation
- update status with verification evidence

### Task 4: Future backend/admin review slice

**Files:**
- Future only; no implementation in this slice.

**Step 1: Add DB staging models and migrations**
**Step 2: Add review/import/publish APIs**
**Step 3: Add admin review UI**
**Step 4: Add publish workflow**

This task is intentionally deferred until the admin surface exists in the rebuild.
