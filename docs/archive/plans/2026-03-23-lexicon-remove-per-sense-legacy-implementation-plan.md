# Lexicon Remove Per-Sense Legacy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the remaining legacy `per_sense` lexicon enrichment mode and the old realtime `enrichments.jsonl` artifact path from the active toolchain.

**Architecture:** Collapse realtime enrichment to per-word only, remove CLI/runtime branching for `per_sense`, and delete downstream compatibility paths that only exist for the retired sense-era artifacts. Update tests and docs so the supported workflow is unambiguous.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSONL artifacts, pytest/unittest.

---

### Task 1: Add failing tests for legacy per-sense removal

**Files:**
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_validate.py`
- Modify: `tools/lexicon/tests/test_canonical_registry.py`
- Modify: `tools/lexicon/tests/test_compile_export.py`

**Step 1: Add CLI failure coverage**

Assert `enrich --mode per_sense` is rejected because the flag no longer supports that mode.

**Step 2: Remove/update runtime tests**

Replace per-sense-specific enrich tests with per-word-only expectations or explicit unsupported-path assertions.

**Step 3: Remove/update artifact-reader tests**

Update compile/validate/canonical-registry tests so `words.enriched.jsonl` is the only supported realtime artifact.

**Step 4: Run focused tests to confirm red**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_canonical_registry.py tools/lexicon/tests/test_compile_export.py -q
```

Expected:

- failures in the old per-sense expectations

### Task 2: Remove per-sense CLI and runtime code

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py`

**Step 1: Remove CLI mode support**

Delete `per_sense` from the enrich parser and help text.

**Step 2: Collapse runtime mode handling**

Delete the per-sense branch in realtime enrichment and simplify destination naming/defaults to per-word only.

**Step 3: Run focused tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py -q
```

Expected:

- CLI/runtime tests pass

### Task 3: Remove legacy downstream artifact compatibility

**Files:**
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/validate.py`
- Modify: `tools/lexicon/canonical_registry.py`
- Modify: related tests under `tools/lexicon/tests/`

**Step 1: Delete old artifact reads**

Stop treating `enrichments.jsonl` as the active realtime artifact.

**Step 2: Keep current compiled workflow intact**

Ensure active snapshot paths still use:

- `words.enriched.jsonl`
- `enrich.checkpoint.jsonl`
- `enrich.decisions.jsonl`
- `enrich.failures.jsonl`

**Step 3: Run focused artifact tests**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_canonical_registry.py tools/lexicon/tests/test_compile_export.py -q
```

Expected:

- downstream tests pass without legacy readers

### Task 4: Update docs and status

**Files:**
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Remove legacy wording**

Delete any remaining mention of `per_sense` as a supported enrich mode.

**Step 2: Record the cleanup**

Add a status log entry and update the lexicon workstream row if needed.

### Task 5: Verification before completion

**Files:**
- No new files expected

**Step 1: Run focused suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_validate.py tools/lexicon/tests/test_canonical_registry.py tools/lexicon/tests/test_compile_export.py -q
```

**Step 2: Run full lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

**Step 3: Compile-check changed Python modules**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m py_compile tools/lexicon/cli.py tools/lexicon/enrich.py tools/lexicon/compile_export.py tools/lexicon/validate.py tools/lexicon/canonical_registry.py
```
