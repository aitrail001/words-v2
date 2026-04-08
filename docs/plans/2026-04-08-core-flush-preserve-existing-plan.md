# Core Flush Preserve Existing Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix staged core enrichment so capped or partial `enrich-core` runs do not overwrite preexisting rows in `words.enriched.core.jsonl` when flushing runtime progress.

**Architecture:** Keep `words.enriched.core.runtime.jsonl` as the resumable in-run artifact, but change finalization so `words.enriched.core.jsonl` is produced by merging existing compiled rows with runtime-derived rows keyed by `entry_id`. Runtime rows should replace stale compiled rows for the same lexeme while untouched compiled rows remain preserved.

**Tech Stack:** Python lexicon pipeline in `tools/lexicon/enrich.py`, pytest regression coverage in `tools/lexicon/tests/test_enrich.py`.

---

### Task 1: Add failing regression coverage for capped staged-core flushes

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`

- [ ] **Step 1: Add a focused test where an existing `words.enriched.core.jsonl` row survives a capped `enrich-core` run that only writes new runtime rows**

```python
def test_run_core_enrichment_preserves_existing_compiled_rows_when_flushing_runtime(self) -> None:
    ...
```

- [ ] **Step 2: Add a focused test where a runtime row replaces the existing compiled row for the same `entry_id`**

```python
def test_run_core_enrichment_runtime_rows_override_existing_compiled_rows(self) -> None:
    ...
```

- [ ] **Step 3: Run the focused tests and confirm they fail against the current overwrite behavior**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q -k 'preserves_existing_compiled_rows_when_flushing_runtime or runtime_rows_override_existing_compiled_rows'`
Expected: FAIL because `run_core_enrichment()` currently rewrites `words.enriched.core.jsonl` from only runtime rows.

### Task 2: Patch core finalization to merge existing compiled output with runtime rows

**Files:**
- Modify: `tools/lexicon/enrich.py`

- [ ] **Step 1: Extract a helper that loads existing compiled core rows, overlays runtime-derived rows by `entry_id`, and writes a deterministic merged output**

```python
def _merge_existing_core_output_with_runtime_rows(...):
    ...
```

- [ ] **Step 2: Update `run_core_enrichment()` to use the merge helper instead of blindly rewriting from runtime rows**

```python
core_rows = [...]
write_jsonl(destination, _merge_existing_core_output_with_runtime_rows(...))
```

- [ ] **Step 3: Keep runtime/checkpoint semantics unchanged**

Run: focused tests from Task 1
Expected: PASS

### Task 3: Record status and verify the staged-core slice

**Files:**
- Modify: `docs/status/project-status.md`

- [ ] **Step 1: Add a concise status entry documenting the staged core flush preservation fix**

```markdown
| 2026-04-08 | No Change. Fixed staged core enrichment so partial/capped runtime flushes merge into existing `words.enriched.core.jsonl` instead of truncating previously compiled rows. | Codex | `...pytest ...` |
```

- [ ] **Step 2: Run the targeted verification slice**

Run: `.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q -k 'preserves_existing_compiled_rows_when_flushing_runtime or runtime_rows_override_existing_compiled_rows or split_legacy_enrich_artifact_can_synthesize_resume_ledgers or prefers_legacy_core_ledgers or rejects_legacy_accepted_rows_missing_from_compiled_output'`
Expected: PASS
