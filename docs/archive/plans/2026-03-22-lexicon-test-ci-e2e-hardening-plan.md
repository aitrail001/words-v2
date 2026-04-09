# Lexicon Test/CI/E2E Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the grouped-phonetics and unified realtime/batch lexicon flow explicitly covered by offline tests, CI smoke, and an end-to-end import-to-API assertion.

**Architecture:** Keep the shipped runtime behavior unchanged. Tighten verification at three layers: lexicon CLI regression tests, CI smoke contract assertions, and Playwright smoke that imports a compiled artifact then validates grouped phonetics through the backend API.

**Tech Stack:** Python unittest/pytest, GitHub Actions, Playwright, backend FastAPI, lexicon CLI JSONL artifacts.

---

### Task 1: Lock the CLI/CI contract in tests

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `.github/workflows/ci.yml`

**Step 1: Write/adjust the failing test**
- Extend the smoke CLI regression so it asserts realtime smoke produces `words.enriched.jsonl` directly and does not require a legacy compile step.
- Assert the produced row includes grouped `phonetics.us/uk/au`.

**Step 2: Run the narrow test**
- Run: `python -m pytest tools/lexicon/tests/test_cli.py -q`

**Step 3: Write the minimal workflow change**
- Update the CI lexicon smoke step to validate the direct realtime artifact contract.
- Remove the outdated extra `compile-export` expectation from the smoke flow.

**Step 4: Re-run the narrow test**
- Run: `python -m pytest tools/lexicon/tests/test_cli.py -q`

### Task 2: Add end-to-end grouped-phonetics verification

**Files:**
- Modify: `e2e/tests/smoke/admin-lexicon-ops-import-flow.smoke.spec.ts`

**Step 1: Extend the compiled fixture**
- Add grouped `phonetics.us/uk/au` to the synthetic compiled word row used by the import smoke.

**Step 2: Add the E2E assertion**
- After the admin import succeeds, query the backend API and assert grouped phonetics are present in the word enrichment response.

**Step 3: Run the narrow E2E smoke**
- Run the existing lexicon ops/import smoke spec only.

### Task 3: Verification and status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run targeted verification**
- `python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_unified_enrichment_flow.py -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_words.py -q`
- relevant Playwright smoke spec

**Step 2: Run the full relevant suites**
- `python -m pytest tools/lexicon/tests -q`
- `PYTHONPATH=backend python -m pytest backend/tests/test_words.py backend/tests/test_models.py backend/tests/test_lexicon_enrichment_models.py -q`

**Step 3: Update status with evidence**
- Add the new CI/E2E coverage and exact commands/results to `docs/status/project-status.md`.
