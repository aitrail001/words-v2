# Local Data-Only Lexicon Policy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate code sync from lexicon runtime artifacts by making `data/` local-only and removing tracked data files from Git.

**Architecture:** Keep existing runtime paths under `data/lexicon/...`, but stop versioning anything under `data/`. Update docs/status to describe the new contract and remove tracked data files from the index while preserving them locally.

**Tech Stack:** Git ignore/index behavior, Markdown docs, existing lexicon CLI/operator workflow.

---

### Task 1: Update repository policy docs

**Files:**
- Modify: `/.gitignore`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Update ignore policy**

- Change the ignore rule from `data/lexicon/` to `data/`.

**Step 2: Update operator guidance**

- State that `data/` is local-only operational storage.
- Keep existing `data/lexicon/...` examples, but clarify they are not Git-synced fixtures.
- Add a short note that pulling new code does not update already running lexicon processes.

**Step 3: Update live status**

- Add a status-log entry documenting the new local-only data policy and why it was adopted.

### Task 2: Remove tracked data from Git control

**Files:**
- Modify: Git index entries under `data/`

**Step 1: Stage tracked data removal**

Run:

```bash
git rm --cached -r data
```

Expected:
- Git stages removal of tracked data files
- Local files remain on disk because removal is index-only

**Step 2: Verify working tree semantics**

Run:

```bash
git status --short
git ls-files 'data/**'
```

Expected:
- no tracked `data/**` entries remain
- status shows the intended staged deletions plus doc changes

### Task 3: Verify and summarize

**Files:**
- No new source files

**Step 1: Run lightweight verification**

Run:

```bash
git diff --stat
rg -n "local-only operational storage|git pull --ff-only" tools/lexicon/OPERATOR_GUIDE.md docs/status/project-status.md .gitignore
```

Expected:
- diff matches docs plus tracked-data removal
- docs contain the new operator contract

**Step 2: Prepare merge summary**

- Report that future code sync requires only normal Git fast-forwarding.
- Report that `data/` artifacts are now intentionally local-only and no longer Git-tracked.
