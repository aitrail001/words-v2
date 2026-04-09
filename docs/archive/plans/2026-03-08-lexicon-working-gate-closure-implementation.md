# Lexicon Working-Gate Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the last three closure slices for the lexicon tool as a working local-DB admin tool.

**Architecture:** Keep the existing offline/admin lexicon architecture intact. Clarify the canonical write path in docs, prove the full path with a clean smoke against the local stack, and freeze a concise operator pass/fail gate. Do not expand the product scope with new UI or major schema features in this closure step.

**Tech Stack:** Existing lexicon CLI, Docker Compose backend/Postgres stack, backend API auth endpoints, Markdown docs/status artifacts.

---

## Task 1 — Canonicalize the final ingestion path

1. Update docs to state that `compile-export -> import-db` is the canonical final DB write path.
2. Clarify that staged review controls selection/review but is not the canonical final learner-enrichment publisher.
3. Record the decision in a small ADR or equivalent technical decision doc.

## Task 2 — Run a clean end-to-end DB smoke

1. Use a clean local stack or isolated DB path.
2. Run:
   - `build-base`
   - `enrich`
   - `validate --snapshot-dir`
   - `compile-export`
   - `validate --compiled-input`
   - `import-db`
3. Verify the imported result through the backend API enrichment inspection endpoint.
4. Capture exact commands and pass/fail evidence.

## Task 3 — Freeze the operator working gate

1. Add a runbook/checklist with explicit preflight, commands, pass criteria, and failure conditions.
2. Separate “working gate v1” from later hardening items.
3. Keep the checklist short and practical.

## Task 4 — Document future TODOs and closure status

1. Add the explicitly deferred items to docs as future-improvement TODOs.
2. Update `docs/status/project-status.md` with closure evidence.
3. Make it clear the tool is closed as a working local-DB admin tool after this gate, with future work tracked separately.
