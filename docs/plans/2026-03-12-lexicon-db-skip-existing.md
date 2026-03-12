# Lexicon DB Skip Existing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `build-base` skip canonical words that already exist in the local word DB by default, while still allowing explicit reruns.

**Architecture:** Reuse the existing backend SQLAlchemy models/config from the lexicon CLI, perform one bulk DB lookup on canonical build candidates after deterministic canonicalization, and record skipped entries in snapshot metadata without generating lexeme/sense rows for them. Keep import semantics unchanged.

**Tech stack:** Python CLI, SQLAlchemy sync lookup, existing lexicon snapshot JSONL artifacts, unittest/pytest.

## Tasks

1. Add failing tests for build-base skip behavior.
2. Add failing tests for CLI flag wiring.
3. Add bulk DB lookup helper in the lexicon CLI.
4. Add canonical-word skip hook in `build_base_records`.
5. Expose `--rerun-existing` and optional `--database-url` on `build-base`.
6. Record skipped-existing counts in build-base JSON output and snapshot status artifacts.
7. Update README/operator docs.
8. Update project status.
9. Run focused and broad lexicon verification.
