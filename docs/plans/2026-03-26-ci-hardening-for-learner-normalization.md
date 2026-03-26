# CI Hardening for Learner Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align GitHub CI with the verified learner/lexicon normalization gate and improve diagnostics for Docker-stack failures.

**Architecture:** Keep the existing single GitHub Actions CI workflow, but tighten the frontend test invocation and the Docker-based E2E jobs so they recreate the stack consistently, surface migration/worker failures immediately, and upload compose logs when the stack or smoke suite fails.

**Tech Stack:** GitHub Actions, Docker Compose, Playwright, npm, pytest.

---

### Task 1: Harden frontend CI test invocations

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1:** Change frontend unit test steps to deterministic CI invocations.

**Step 2:** Keep build steps unchanged.

### Task 2: Harden Docker E2E job startup and diagnostics

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1:** Add `--force-recreate` to the compose startup for `e2e-smoke` and `e2e-full`.

**Step 2:** Expand readiness-failure logging to include `migrate`, `worker`, `backend`, `frontend`, and `admin-frontend` where relevant.

**Step 3:** Add a compose-log collection step that runs on failure before artifact upload.

### Task 3: Update status and verify changed scope

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1:** Record the CI hardening change and why it was needed.

**Step 2:** Run the smallest verification needed for the workflow change and report what was not run directly on GitHub.
