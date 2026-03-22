# Lexicon Realtime/Batch Unification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify realtime and batch lexicon enrichment around one shared word-level QC/materialization path, remove compile from realtime enrichment, and emit review-ready `words.enriched.jsonl` plus regenerate/failure artifacts.

**Architecture:** Realtime enrichment will read only `lexemes.jsonl`, generate one word payload at a time, run shared validation/QC/materialization immediately, regenerate inline on failure, and append only accepted compiled word rows to `words.enriched.jsonl`. Batch ingestion will preserve its async ledger flow, but after ingest it will call the same shared finalization logic to split outputs into accepted `words.enriched.jsonl` rows and a regenerate queue, eliminating divergent quality gates between realtime and batch.

**Tech Stack:** Python CLI tooling in `tools/lexicon`, JSONL snapshot artifacts, unittest/pytest lexicon tests, admin workflow docs, local OpenAI-compatible endpoint for low-cost smoke verification.

---

### Task 1: Lock Shared File Contracts

**Files:**
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/validate.py`
- Modify: `tools/lexicon/compile_export.py`
- Test: `tools/lexicon/tests/test_compile_export.py`

**Step 1: Write the failing tests**

Add tests that assert:
- realtime/finalized word rows no longer require `senses.jsonl` to compile word output
- shared compiled-record validation is the gate for both realtime and batch accepted output
- review queue sidecars are no longer required for realtime accepted output

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py -q`
Expected: FAIL on the new contract assertions.

**Step 3: Write minimal implementation**

Update the shared models/validation helpers so compiled word records can be materialized directly from word-level generation output without a snapshot `senses.jsonl` dependency.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py -q`
Expected: PASS.

### Task 2: Refactor Realtime Enrichment To Finalize Inline

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write the failing tests**

Add tests that assert:
- realtime enrichment reads only `lexemes.jsonl`
- realtime writes accepted rows directly to `words.enriched.jsonl`
- inline QC/materialization retries invalid payloads before persisting
- checkpoint/decision/failure sidecars still support resume
- obsolete `per_sense` realtime behavior is no longer exposed

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: FAIL on the new realtime output/contract assertions.

**Step 3: Write minimal implementation**

Refactor `enrich.py` so the realtime path:
- loads only `lexemes.jsonl`
- validates/materializes each word result with the shared finalizer
- appends only accepted compiled rows to `words.enriched.jsonl`
- records failed-after-budget rows in `enrich.failures.jsonl`

Update the CLI to default to the new realtime contract and remove dead per-sense flags if they are no longer supported.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`
Expected: PASS.

### Task 3: Reuse The Same Finalizer For Batch

**Files:**
- Modify: `tools/lexicon/batch_ingest.py`
- Modify: `tools/lexicon/batch_prepare.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/qc.py`
- Test: `tools/lexicon/tests/test_batch_ingest.py`
- Test: `tools/lexicon/tests/test_batch_lifecycle.py`

**Step 1: Write the failing tests**

Add tests that assert:
- batch finalize emits accepted `words.enriched.jsonl`
- failed batch rows are written to a regenerate queue artifact for human rerun
- batch CLI/status payloads report the new accepted/regenerate outputs
- batch QC uses the same shared validation/materialization contract as realtime

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_batch_ingest.py tools/lexicon/tests/test_batch_lifecycle.py -q`
Expected: FAIL on the new finalize/regenerate queue assertions.

**Step 3: Write minimal implementation**

Refactor batch ingest/finalize so accepted rows flow into `words.enriched.jsonl`, failing rows flow into a regenerate queue JSONL, and duplicate compile/QC logic is removed in favor of the shared word-level finalizer.

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_batch_ingest.py tools/lexicon/tests/test_batch_lifecycle.py -q`
Expected: PASS.

### Task 4: Remove Obsolete Realtime Snapshot Dependencies And Update Docs

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `tools/lexicon/README.md`
- Modify: `docs/status/project-status.md`
- Test: `tools/lexicon/tests/test_cli_canonical_registry.py`

**Step 1: Write the failing test**

Add or adjust a narrow CLI/operator-facing test for the updated artifact contract if needed.

**Step 2: Run test to verify it fails**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli_canonical_registry.py -q`
Expected: FAIL only if the docs/CLI-visible contract test needs updating.

**Step 3: Write minimal implementation**

Update docs/status to reflect:
- realtime now writes final `words.enriched.jsonl` directly
- batch finalization reuses the same QC/materialization logic
- `senses.jsonl` and review sidecars are no longer part of the realtime happy path

**Step 4: Run test to verify it passes**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli_canonical_registry.py -q`
Expected: PASS.

### Task 5: Full Verification And Low-Cost Live Checks

**Files:**
- Verify: `tools/lexicon/enrich.py`
- Verify: `tools/lexicon/batch_ingest.py`
- Verify: `tools/lexicon/compile_export.py`
- Verify: `tools/lexicon/cli.py`
- Verify: `tools/lexicon/tests/test_enrich.py`
- Verify: `tools/lexicon/tests/test_compile_export.py`
- Verify: `tools/lexicon/tests/test_batch_ingest.py`
- Verify: `tools/lexicon/tests/test_batch_lifecycle.py`

**Step 1: Run targeted lexicon tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_batch_ingest.py tools/lexicon/tests/test_batch_lifecycle.py -q`
Expected: PASS.

**Step 2: Run broader lexicon verification**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
Expected: PASS.

**Step 3: Run lint/compile verification for changed Python files**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m py_compile tools/lexicon/enrich.py tools/lexicon/batch_ingest.py tools/lexicon/batch_prepare.py tools/lexicon/compile_export.py tools/lexicon/cli.py tools/lexicon/qc.py tools/lexicon/validate.py`
Expected: PASS.

**Step 4: Run low-cost live realtime smoke**

Run: `set -a && source tools/lexicon/.env.local && set +a && /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli smoke-openai-compatible --output-dir /tmp/lexicon-realtime-smoke-20260322 --max-words 1 --provider-mode openai_compatible --model \"$LEXICON_LLM_MODEL\" --reasoning-effort low run`
Expected: PASS with one-word realtime finalization through the local endpoint.

**Step 5: Run low-cost batch finalize smoke**

Run a minimal one-word batch request/ingest/finalize path using the configured batch keys and assert accepted output plus regenerate queue behavior with tiny fixtures.

**Step 6: Run relevant admin/backend E2E coverage if contract changes reach review/import surfaces**

Run only the narrowest impacted suites after confirming which APIs or UI contracts changed.

