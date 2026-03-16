# Lexicon 30K Rollout Operations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare and run the live 30K lexicon enrichment rollout with resumable artifact-first outputs and milestone-based DB preview imports.

**Architecture:** Reuse the existing curated deterministic 30K snapshot as the base, copy it into a new dated rollout snapshot, run real per-word enrichment in that snapshot with checkpoint/failure sidecars, and periodically compile/import the current artifact state into the local DB for inspection. Keep the canonical truth in `data/lexicon/snapshots/...` and treat the DB as a refreshable projection only.

**Tech Stack:** Python 3.13 CLI in `tools/lexicon`, JSONL snapshot artifacts, OpenAI-compatible Node transport, Docker local stack, local Postgres import path.

---

### Task 1: Document the live rollout path and operational policy

**Files:**
- Create: `docs/plans/2026-03-16-lexicon-30k-rollout-ops-design.md`
- Create: `docs/plans/2026-03-16-lexicon-30k-rollout-ops-plan.md`

**Step 1: Write the approved design**

Capture:

- one-snapshot resumable rollout shape
- `250` first milestone, then `500`
- preview-import cadence
- single-word model policy
- DB as projection, not canonical storage

**Step 2: Write the execution plan**

Capture the concrete operator steps for this session.

**Step 3: Review the design docs**

Run:

```bash
sed -n '1,220p' docs/plans/2026-03-16-lexicon-30k-rollout-ops-design.md
sed -n '1,260p' docs/plans/2026-03-16-lexicon-30k-rollout-ops-plan.md
```

Expected:

- both docs exist
- the workflow is explicit and consistent with the current lexicon tool behavior

### Task 2: Prepare the live 30K rollout snapshot directory

**Files:**
- Create: `data/lexicon/snapshots/<new-run-dir>/...`

**Step 1: Choose the run directory**

Use a new dated directory under `data/lexicon/snapshots/`.

**Step 2: Seed it from the curated deterministic base snapshot**

Copy the current 30K curated snapshot into the new run directory instead of mutating the original base snapshot.

**Step 3: Verify seeded file counts**

Run:

```bash
wc -l data/lexicon/snapshots/<new-run-dir>/{lexemes,senses,concepts,ambiguous_forms}.jsonl
```

Expected:

- `30000` lexemes
- `63126` senses
- `56507` concepts
- `0` ambiguous forms

### Task 3: Validate environment and DB import target

**Files:**
- No repo file changes required

**Step 1: Confirm the words Docker stack is up**

Run:

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
```

Expected:

- `words-backend`, `words-worker`, `words-postgres`, `words-redis`, and relevant frontend containers are running

**Step 2: Confirm lexicon env is available**

Check the shell environment and the Node transport dependency under `tools/lexicon/node`.

**Step 3: Refresh the stack only if needed**

If import or API inspection later shows runtime drift, refresh the stack then, not pre-emptively.

### Task 4: Run the first live 250-word enrichment milestone

**Files:**
- Modify in snapshot dir only: `enrichments.jsonl`, `enrich.checkpoint.jsonl`, `enrich.failures.jsonl`

**Step 1: Start the live enrich run against the new rollout snapshot**

Use:

- `--mode per_word`
- single-word request path
- `gpt-5-nano`
- node transport
- resumable checkpoint/failure outputs inside the snapshot directory

**Step 2: Bound the first milestone to 250 completed lexemes**

If the CLI has no direct stop-at-N flag, monitor the checkpoint and stop after the first safe milestone.

**Step 3: Record the live artifact state**

Inspect:

- completed checkpoint count
- current failure rows
- enrichments line count

Expected:

- outputs are flushing incrementally
- checkpoint is advancing
- any failures are bounded and explainable

### Task 5: Compile, validate, and preview-import the first milestone

**Files:**
- Create/Modify in snapshot dir: `words.enriched.jsonl`

**Step 1: Compile the current snapshot state**

Run:

```bash
python3 -m tools.lexicon.cli compile-export --snapshot-dir data/lexicon/snapshots/<new-run-dir> --output data/lexicon/snapshots/<new-run-dir>/words.enriched.jsonl
```

**Step 2: Validate the compiled export**

Run:

```bash
python3 -m tools.lexicon.cli validate --compiled-input data/lexicon/snapshots/<new-run-dir>/words.enriched.jsonl
```

Expected:

- zero validation errors

**Step 3: Import into the local DB**

Run:

```bash
python3 -m tools.lexicon.cli import-db --input data/lexicon/snapshots/<new-run-dir>/words.enriched.jsonl --source-type lexicon_snapshot --source-reference <new-run-dir> --language en
```

Expected:

- import succeeds
- DB becomes inspectable in the running local stack

### Task 6: Decide whether to continue with 500-word milestones

**Files:**
- No repo file changes required

**Step 1: Review milestone health**

Check:

- failure count and repetition pattern
- compiled validation state
- import success
- inspection usefulness

**Step 2: Continue or pause**

If the first milestone is healthy, continue with repeated `500`-word milestones using `--resume`.
If unhealthy, stop and fix the blocking issue before continuing.

### Task 7: Refresh live status and runbook notes if workflow changes

**Files:**
- Modify as needed: `docs/status/project-status.md`
- Modify as needed: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Update docs only if the actual operating guidance changed**

Do not create status noise if no new reusable behavior was introduced.

### Task 8: Verification before completion

**Files:**
- No new files expected

**Step 1: Verify the active branch state**

Run:

```bash
git status --short --branch
```

**Step 2: Verify the live artifact evidence**

Run the exact commands used for:

- checkpoint counts
- compiled validation
- import confirmation

**Step 3: Report what is complete and what remains live**

Distinguish clearly between:

- repo changes
- live rollout progress
- any remaining long-running enrichment work
