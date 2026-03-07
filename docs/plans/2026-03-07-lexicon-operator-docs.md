# Lexicon Operator Docs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a tool-local lexicon operator guide and `.env.example`, plus a root `.env.example` pointer, so admin operators can run the offline lexicon pipeline safely.

**Architecture:** Keep lexicon operator setup separate from app runtime configuration by placing the detailed example env file and guide under `tools/lexicon/`. Add only a short pointer in the root `.env.example`, and record the documentation update in the status board.

**Tech Stack:** Markdown docs, dotenv-style example files, existing Python lexicon CLI.

---

### Task 1: Capture current lexicon operator context

**Files:**
- Read: `tools/lexicon/README.md`
- Read: `.env.example`
- Read: `docs/status/project-status.md`

**Steps:**
1. review the current lexicon README commands and env names
2. review the root env example style and current lexicon section
3. identify the minimum operator fields the tool-local example must cover

**Verification:**
- confirm the planned fields match the current lexicon CLI/operator flow

### Task 2: Add tool-local operator env example

**Files:**
- Create: `tools/lexicon/.env.example`

**Steps:**
1. add WordNet/wordfreq install guidance comments
2. add snapshot/output examples and DB import variables
3. add real-endpoint variables including `LEXICON_LLM_TRANSPORT=node`
4. keep placeholders safe and never include live secrets

**Verification:**
- inspect the file for safe placeholders and accurate variable names

### Task 3: Add tool-local operator guide and root pointer

**Files:**
- Create: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `tools/lexicon/README.md`
- Modify: `.env.example`

**Steps:**
1. write a concise operator guide for setup, build-base, enrich, validate, compile-export, and import-db
2. document the custom OpenAI-compatible gateway path and Node transport
3. add a short pointer in the root `.env.example` to the tool-local env example and guide
4. keep the root env example compact instead of duplicating full lexicon operator setup

**Verification:**
- re-read the docs to confirm commands, filenames, and env names line up exactly

### Task 4: Update status and verify docs slice

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. add a short status entry for the operator docs/env example slice
2. run targeted verification for the touched files
3. capture exact command output for the final handoff

**Verification:**
- `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
- `python3 -m py_compile tools/lexicon/config.py tools/lexicon/enrich.py tools/lexicon/cli.py`
