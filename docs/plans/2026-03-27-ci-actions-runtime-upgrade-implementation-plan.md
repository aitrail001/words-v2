# CI Actions Runtime Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade GitHub Actions workflow dependencies to the latest stable upstream releases so CI stops relying on deprecated Node 20-hosted action runtimes.

**Architecture:** Keep the workflow shape unchanged and only replace action version pins in `.github/workflows/ci.yml`. Record the governance change and verification evidence in the status board so the repo has a clear audit trail.

**Tech Stack:** GitHub Actions, YAML, GitHub CLI

---

### Task 1: Upgrade action pins

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Confirm upstream stable releases**

Use official GitHub release metadata for:
- `actions/checkout`
- `actions/setup-node`
- `actions/setup-python`
- `actions/cache`

**Step 2: Update workflow pins**

Replace the current versions with the latest stable tags:
- `actions/checkout@v6.0.2`
- `actions/setup-node@v6.3.0`
- `actions/setup-python@v6.2.0`
- `actions/cache@v5.0.4`

**Step 3: Keep workflow behavior unchanged**

Do not change:
- job names
- job dependencies
- build/test commands
- required-vs-optional gate semantics

### Task 2: Record the CI governance change

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Add a dated status entry**

Record:
- the action version upgrades
- the reason for the upgrade
- the local verification command/output

### Task 3: Verify workflow syntax

**Files:**
- Verify: `.github/workflows/ci.yml`

**Step 1: Parse workflow YAML**

Run:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "ci.yml ok"'
```

Expected:
- output includes `ci.yml ok`

### Task 4: Commit and open PR

**Files:**
- Commit only:
  - `.github/workflows/ci.yml`
  - `docs/plans/2026-03-27-ci-actions-runtime-upgrade-implementation-plan.md`
  - `docs/status/project-status.md`

**Step 1: Commit**

Use a focused message such as:

```bash
git commit -m "ci: upgrade github action versions"
```

**Step 2: Push and open PR**

Let GitHub CI verify the workflow change on the branch.
