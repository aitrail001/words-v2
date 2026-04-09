# Voice Generate Resume Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real resume semantics to `voice-generate` so reruns skip already finished work by prior ledgers and can retry only failed units without relying only on file existence.

**Architecture:** Keep `voice-generate` append-only and output-dir scoped. Add a resume mode that reads `voice_manifest.jsonl` and `voice_errors.jsonl`, computes completed and failed `unit_id` sets, filters planned work before dispatch, and preserves deterministic output paths. Expose resume controls through CLI flags and document the operator flow.

**Tech Stack:** Python CLI, JSONL ledgers, unittest, lexicon operator docs

---

### Task 1: Add failing resume tests

**Files:**
- Modify: `tools/lexicon/tests/test_voice_generate.py`

Steps:
1. Add a failing test proving `resume=True` skips units already present in `voice_manifest.jsonl` even if the output file is missing.
2. Add a failing test proving `resume=True` retries units listed only in `voice_errors.jsonl`.
3. Run the focused pytest target and confirm the new tests fail for the expected reason.

### Task 2: Implement ledger-driven resume filtering

**Files:**
- Modify: `tools/lexicon/voice_generate.py`
- Modify: `tools/lexicon/cli.py`

Steps:
1. Add helpers to load prior manifest/error rows and derive completed/failed `unit_id` sets.
2. Extend `run_voice_generation()` with `resume` and `retry_failed_only` options.
3. Filter planned units before dispatch:
   - skip completed units when `resume=True`
   - if `retry_failed_only=True`, run only failed units not already completed
4. Return summary counts that reflect filtered work.
5. Add CLI flags for the new behavior.

### Task 3: Update operator docs

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

Steps:
1. Document `--resume` and `--retry-failed-only`.
2. Clarify the difference between file-existence skipping and ledger-driven resume.

### Task 4: Verify and record evidence

**Files:**
- None

Steps:
1. Run focused lexicon pytest for `test_voice_generate.py` and `test_cli.py`.
2. If green, report exact command output.
