# Lexicon Large-Run Hardening PR B Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `enrich --mode per_word` resilient enough for 1K -> 5K -> 30K operator runs by adding checkpointed incremental writes, resumable execution, failure ledgers, and request pacing.

**Architecture:** Keep the downstream artifact shape (`enrichments.jsonl`) unchanged, but stop treating per-word enrichment as an all-or-nothing in-memory batch. Instead, append completed lexeme records as they finish, write a checkpoint row per lexeme, skip completed lexemes on `--resume`, and persist failures separately so operators can continue large runs safely.

**Tech Stack:** Python 3.13, existing lexicon CLI/enrichment pipeline, JSONL artifacts, pytest.

---

### Task 1: Add failing tests for checkpoint/resume behavior

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Steps:**
1. Add a per-word enrichment test that writes one lexeme, fails on the next, and confirms partial output + checkpoint are preserved.
2. Add a resume test that reruns with `--resume` and skips already-completed lexemes.
3. Add a CLI test asserting new flags are passed into `run_enrichment`.
4. Run targeted tests and confirm failure.

### Task 2: Add append/checkpoint primitives

**Files:**
- Modify: `tools/lexicon/jsonl_io.py`
- Modify: `tools/lexicon/enrich.py`

**Steps:**
1. Add JSONL append helper(s).
2. Add checkpoint/failure row helpers for per-word runs.
3. Keep existing full-write behavior for other flows.

### Task 3: Implement resilient per-word enrichment

**Files:**
- Modify: `tools/lexicon/enrich.py`

**Steps:**
1. Add per-word-only arguments for `resume`, `checkpoint_path`, `failures_output`, `max_failures`, and `request_delay_seconds`.
2. On fresh run, initialize/truncate artifacts.
3. On resume, load checkpoint and skip completed lexemes.
4. Append completed enrichment rows as each lexeme finishes.
5. Append failure rows without losing prior completed work.
6. Raise only when the configured failure threshold is exceeded.

### Task 4: Expose operator controls in CLI

**Files:**
- Modify: `tools/lexicon/cli.py`

**Steps:**
1. Add CLI flags for checkpoint/resume/failure controls.
2. Thread them through to `run_enrichment`.
3. Keep defaults backwards-compatible.

### Task 5: Update docs and status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Document 1K -> 5K -> 30K operator guidance using `--resume` and checkpoint files.
2. Document what gets written during a large run.
3. Add fresh verification evidence to the status board.

### Task 6: Verify, commit, PR, merge, clean up

**Verification:**
- Targeted `test_enrich.py` + `test_cli.py`
- Full lexicon suite
- Real placeholder smoke with forced resume path
- Fresh diff review before commit
