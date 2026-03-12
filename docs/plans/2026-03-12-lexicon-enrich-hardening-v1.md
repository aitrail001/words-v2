# Lexicon Enrichment Hardening V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve real-world completion rate for per-word lexicon enrichment runs without changing the learner-facing data model.

**Architecture:** Harden the existing OpenAI-compatible enrichment path rather than redesigning the pipeline. Add bounded robustness at the transport/payload boundary: configurable timeout, salvage parsing for noisy JSON text, stronger repair prompts, and bounded repair retries for repairable validation failures. Keep import/output schema unchanged.

## Tasks

1. Write focused failing tests for JSON salvage, numeric-string confidence coercion, timeout config, and multi-attempt repair.
2. Run the focused lexicon tests and confirm the new tests fail for the current implementation.
3. Implement timeout configuration in `tools/lexicon/config.py` and `tools/lexicon/enrich.py`.
4. Implement JSON text salvage and bounded repair retries in `tools/lexicon/enrich.py`.
5. Strengthen the per-word prompt with explicit translation-shape rules.
6. Re-run the focused lexicon tests and fix any regressions.
7. Resume the stalled 1K enrichment snapshot with lower concurrency / request pacing as needed.
8. If enrichment completes sufficiently, run `validate`, `compile-export`, and an import smoke.
9. Update `docs/status/project-status.md` with evidence if rollout state meaningfully changes.
