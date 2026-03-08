# Python Runtime Standardization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize repo-local stable Python environments on the project runtime available on this machine and document how virtualenvs should be handled with worktrees.

**Architecture:** Use repo-root virtualenvs as the only durable Python environments, recreate them with the official local runtime for this repo, and document that worktree-local virtualenvs are disposable and should not be treated as durable state.

**Tech Stack:** Python 3.13 virtualenvs, pip requirements files, git worktrees, repo documentation.

---

## Task 1 — Confirm available runtimes and repo signals

1. Check which Python interpreters are installed locally.
2. Check repo docs and CI/runtime declarations.
3. Choose one stable local runtime that is both available and aligned with the repo.

## Task 2 — Recreate stable root backend env

1. Remove or replace the temporary root backend env.
2. Create `/Users/johnson/AI/src/words-v2/.venv-backend` with the chosen Python runtime.
3. Install backend dependencies needed for normal repo-local backend work.

## Task 3 — Recreate stable root lexicon env

1. Remove or replace any old lexicon env.
2. Create `/Users/johnson/AI/src/words-v2/.venv-lexicon` with the same runtime.
3. Install lexicon tool dependencies.

## Task 4 — Document env handling policy

1. Update the most relevant repo doc(s) with the chosen Python runtime.
2. State that durable venvs live at repo root, not inside disposable worktrees.
3. State how to handle temporary experimental worktree envs if ever needed.

## Task 5 — Verify and report

1. Verify both envs report the expected Python version.
2. Verify key commands import/run successfully.
3. Verify git status remains clean.
