# Refresh lexicon fixtures and seed review data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the dev lexicon DB from the specified reviewed snapshots, refresh the checked-in `tests/fixtures/lexicon-db/smoke` export from that DB, document the local-only `full` export refresh path, and seed learner review entries for `user@user.com`.

**Architecture:** Use the existing Docker dev stack plus backend/admin APIs and lexicon CLI commands already in the repo. Keep the work isolated in a dedicated worktree, use server-side bulk approval/materialization for the two snapshots, then import/export through the supported CLI and finally seed review state through the live backend DB.

**Tech Stack:** Docker Compose, FastAPI backend, admin review APIs, Postgres, `tools/lexicon` CLI, learner review services.

---

### Task 1: Discover the exact operational entry points

**Files:**
- Inspect: `scripts/*.sh`
- Inspect: `backend/app/api/lexicon_compiled_reviews.py`
- Inspect: `backend/app/api/lexicon_jobs.py`
- Inspect: `tools/lexicon/cli.py`
- Inspect: `tools/lexicon/export_db.py`
- Inspect: `tools/lexicon/import_db.py`
- Inspect: learner review models/services used to seed review rows

**Step 1:** Find the snapshot-review, materialize, import, export, and review-seeding commands or APIs.

**Step 2:** Confirm the exact source paths for:
- `words-40000-20260323-main-wordfreq-live-target30k`
- `phrases-7488-20260323-reviewed-phrasals-idioms-v1`

**Step 3:** Confirm where `tests/fixtures/lexicon-db/smoke` should be written and how the oversized local-only `full` export should be regenerated.

### Task 2: Bring up the dev stack and prepare data

**Files:**
- Operate on Docker stack only

**Step 1:** Start the repo dev stack.

**Step 2:** Run any required migrations.

**Step 3:** Verify backend/admin/frontend are reachable before mutating data.

### Task 3: Approve and materialize the two reviewed snapshots

**Files:**
- No source edits expected unless a command bug is found

**Step 1:** Create or locate compiled review batches for the two named snapshots.

**Step 2:** Bulk-approve all pending items server-side.

**Step 3:** Materialize approved outputs for each batch.

**Step 4:** Verify the approved artifacts exist on disk.

### Task 4: Import approved outputs and refresh checked-in fixtures

**Files:**
- Replace: `tests/fixtures/lexicon-db/smoke/approved.jsonl`
- Document local-only regeneration for: `tests/fixtures/lexicon-db/full/approved.jsonl`

**Step 1:** Import the approved outputs into the dev DB using the supported import path.

**Step 2:** Export a fresh full fixture from the DB for local operator use, but do not commit it if it exceeds GitHub file limits.

**Step 3:** Export or derive the smoke fixture from the DB using the repo’s supported fixture flow and commit that refreshed smoke fixture.

**Step 4:** Verify the refreshed smoke fixture exists and contains rows, and record the local full-export counts for operators.

### Task 5: Seed learner review data for user@user.com

**Files:**
- No source edits expected unless a seeding bug is found

**Step 1:** Locate `user@user.com` in the dev DB.

**Step 2:** Create due learner review entries against imported words/phrases using the current entry-review schema/service path.

**Step 3:** Verify the user has due review items.

### Task 6: Record evidence and report final state

**Files:**
- Update: `docs/status/project-status.md` only if system state or operator workflow status changed materially

**Step 1:** Capture the exact commands and counts used for import/export/seeding verification.

**Step 2:** Report what was refreshed and what remains manual.
