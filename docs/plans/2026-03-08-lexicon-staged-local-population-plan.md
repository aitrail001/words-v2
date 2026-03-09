# Lexicon Staged Local Population Plan (100 -> 1,000 -> 2,000)

**Goal:** Populate a useful local database for realistic app and API testing without jumping directly to a large lexicon import that would make cleanup, tuning, or rollback expensive.

**Primary outcome:** A controlled staged rollout path for local lexicon data population using the existing canonical admin pipeline:

1. `build-base`
2. optional review-prep flow
3. `enrich`
4. `validate --snapshot-dir`
5. `compile-export`
6. `validate --compiled-input`
7. `import-db`

**Why stage it:**
- validate learner-facing content quality before large local imports
- catch selector/prompt/import surprises early
- keep rollback and cleanup simple
- create a progressively more realistic local DB for app feature testing

## Scope

This plan is for **local operator population**, not CI and not pre-prod release verification.

It assumes:
- the lexicon tool is already working end to end
- local backend + Postgres are available
- a real OpenAI-compatible enrichment path can be used when desired
- the operator wants progressively richer local data to test app behavior

## Core policy

Do **not** jump straight from empty or lightly populated local DBs to a 2,000-word real import.

Use this progression:

- Stage 1: `100` words
- Stage 2: `1,000` words
- Stage 3: `2,000` words

Advance only if the previous stage passes its acceptance checks.

## Data/DB strategy

Use a rollback-friendly approach for every stage.

Recommended order:

1. create a DB backup or a dedicated clone before the first real staged import
2. use a unique `source_reference` per stage
3. keep the snapshot directory and compiled JSONL for every stage
4. record import summaries and API/UI inspection notes

Recommended `source_reference` pattern:

- `lexicon-local-stage100-YYYYMMDD`
- `lexicon-local-stage1000-YYYYMMDD`
- `lexicon-local-stage2000-YYYYMMDD`

If you expect to re-run a stage multiple times in one day, include a suffix:

- `lexicon-local-stage100-YYYYMMDD-r1`
- `lexicon-local-stage100-YYYYMMDD-r2`

## Word selection policy

Prefer frequency-first seed sets.

Recommended composition:
- mostly high-frequency general English words
- a mix of verbs, nouns, adjectives, and adverbs
- enough polysemous words to expose selector weaknesses
- avoid starting with too many obscure or domain-heavy words

Suggested staged composition:

### Stage 1 (`100` words)
Use a curated high-frequency sample for fast quality review.

Purpose:
- verify the local product is useful with real imported data
- inspect common learner-facing fields
- catch prompt/selection problems cheaply

### Stage 2 (`1,000` words)
Use a broader high-frequency slice after Stage 1 passes.

Purpose:
- test search, detail, enrichment display, and performance on a realistic working local dataset
- identify recurring content-quality issues at moderate scale

### Stage 3 (`2,000` words)
Use a larger but still manageable working set.

Purpose:
- create a strong local testing corpus for broader app work
- validate whether the current selector/prompt quality is good enough before even larger imports

## Stage 0: Preflight and rollback point

Before Stage 1:

1. confirm backend migrations are current
2. confirm WordNet corpora and lexicon env are installed
3. confirm the chosen LLM endpoint/model/transport are working
4. create a DB backup or a clone DB for the staged rollout
5. choose whether the test target is:
   - a dedicated local clone DB, or
   - the main local dev DB after backup

Recommended operator rule:
- use a **clone DB** for Stage 1 if you are still evaluating content quality
- move to your main local working DB only after Stage 1 looks good

## Stage 1: 100-word rollout

### Objective
Prove that real imported learner-facing data is good enough to start product testing.

### Run shape
- real enrichment preferred
- bounded but realistic word list
- import into rollback-safe local DB target

### Required commands

Use the canonical path:

```bash
python3 -m tools.lexicon.cli build-base --output-dir <snapshot_dir> $(cat <word_list_file>)
python3 -m tools.lexicon.cli enrich --snapshot-dir <snapshot_dir> --provider-mode auto --model <model> --reasoning-effort low
python3 -m tools.lexicon.cli validate --snapshot-dir <snapshot_dir>
python3 -m tools.lexicon.cli compile-export --snapshot-dir <snapshot_dir> --output <snapshot_dir>/words.enriched.jsonl
python3 -m tools.lexicon.cli validate --compiled-input <snapshot_dir>/words.enriched.jsonl
python3 -m tools.lexicon.cli import-db --input <snapshot_dir>/words.enriched.jsonl --source-type lexicon_snapshot --source-reference <stage_source_reference> --language en
```

### Acceptance checks
All of these must pass before moving to Stage 2:

1. pipeline checks
- snapshot validation returns zero errors
- compiled validation returns zero errors
- import succeeds without partial failure

2. content spot checks
- inspect at least `20` words manually
- include at least:
  - `10` very common words
  - `5` polysemous words
  - `5` mixed POS words
- check:
  - CEFR feels plausible
  - top senses are learner-useful
  - examples are natural
  - confusable words are helpful, not noisy
  - grammar patterns are not empty/noisy for common verbs

3. API checks
- `GET /api/words/{word_id}/enrichment` works for multiple imported words
- meaning examples and difficulties are visible
- relations and learner-facing fields are present where expected

4. product checks
- search imported words through the app
- open detail/enrichment views for at least `10` imported words
- note any obvious UI/readability issues caused by real data length or shape

### Stop criteria
Do **not** advance if you see repeated problems such as:
- weak or confusing primary senses
- CEFR obviously too high/low for many common words
- noisy confusable-word lists
- repetitive or unnatural examples
- major import/update/API inconsistencies

### Decision
- pass -> proceed to Stage 2
- fail -> tune selector/prompt/import behavior first, then rerun Stage 1

## Stage 2: 1,000-word rollout

### Objective
Create the first truly useful local testing dataset.

### Objective details
This stage is for testing the app with a realistic working corpus, not just proving the pipeline works.

### Acceptance checks
All Stage 1 checks still apply, plus:

1. import/runtime checks
- capture full import summary
- measure rough import duration
- confirm app/API responsiveness remains acceptable on common flows

2. broader content review
- inspect at least `50` words sampled across:
  - top frequency words
  - high-polysemy words
  - verbs with many senses
  - nouns with domain drift
  - adjectives/adverbs
- note recurring failure patterns, not just one-off bad rows

3. product behavior checks
- search should feel useful across many common words
- word detail/enrichment pages should stay readable with richer meanings/examples
- any feature that depends on `words`/`meanings` should be exercised on imported data

4. update-path sanity
- optionally rerun a tiny overlapping import on a subset to confirm update/idempotent behavior is still acceptable

### Stop criteria
Do **not** advance if:
- bad patterns are systematic rather than isolated
- import performance is poor enough to slow local iteration badly
- the app becomes hard to use because of overly verbose or noisy learner content
- you need schema/UI fixes before the data is actually useful

### Decision
- pass -> proceed to Stage 3
- fail -> keep the 1,000-word dataset as the working corpus, fix issues, then repeat Stage 2

## Stage 3: 2,000-word rollout

### Objective
Create a strong broader local corpus for feature development and exploratory testing.

### Acceptance checks
- Stage 2 checks remain acceptable
- no major product regressions from the larger corpus
- search/detail/enrichment remain practical to use
- the imported dataset is stable enough that other feature work can rely on it

### Outcome
If Stage 3 passes, this can become the default populated local DB for broader feature testing.

## Operator checklist by stage

For every stage, keep this evidence:
- word list file used
- snapshot directory
- compiled JSONL output
- exact commands
- import summary JSON output
- API readback examples for at least a few words
- short review notes: what looked good, what looked bad, whether to advance

## Suggested advancement thresholds

Use these as practical heuristics:

### Move from 100 -> 1,000 only if
- no structural import/API problems
- most inspected words look reasonable
- bad rows are isolated, not systemic
- the app already benefits from the imported dataset

### Move from 1,000 -> 2,000 only if
- recurring quality issues are acceptable or already understood
- app behavior remains usable with the broader corpus
- you want the DB primarily for product testing rather than prompt tuning

## Cleanup / rollback guidance

If a stage is not good enough:
- restore from DB backup, or
- switch back to the pre-stage clone DB, or
- keep the failed dataset isolated and do not make it your main local working DB

Do not rely on ad hoc manual cleanup after large imports if you can avoid it.

## Recommended next action

Run Stage 1 first with a curated `100`-word list and real enrichment.

If Stage 1 passes:
- keep the same operator flow
- increase to `1,000`
- use that dataset for real app testing before deciding whether the jump to `2,000` is worthwhile

## Future hardening beyond this plan

This plan does not replace future work such as:
- stronger compiled validation
- explicit review-status gating before import
- batch checkpoint/retry/budget controls
- dedicated admin review UI
- automated DB-backed lexicon import smoke in CI
