# Lexicon 30K Next Pass Execution Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the deterministic 30K hardening passes for non-general entity categorization and bounded tail-drop exclusions, then rebuild and verify the exact 30K snapshot.

**Architecture:** Keep policy in tracked datasets rather than widening canonical heuristics. Extend snapshot/base metadata only where needed to carry explicit category signals into later LLM prompting, and use bounded drop lists for concrete low-quality admissions. Rebuild the exact 30K boundary after the data pass and refresh audit/docs from fresh evidence.

**Tech Stack:** Python 3.13, `tools/lexicon` build-base pipeline, JSON/JSONL tracked datasets, pytest, local CLI audit scripts.

---

### Task 1: Add tracked datasets for entity categorization and bounded tail drops

**Files:**
- Create: `tools/lexicon/data/entity_categories.json`
- Create: `tools/lexicon/data/tail_exclusions.json`
- Modify: `tools/lexicon/wordfreq_utils.py`
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/models.py`
- Test: `tools/lexicon/tests/test_build_base.py`
- Test: `tools/lexicon/tests/test_models.py`

### Task 2: Teach the audit path to surface entity categories in reports

**Files:**
- Modify: `tools/lexicon/audit_30k_semantics.py`
- Test: `tools/lexicon/tests/test_audit_30k_semantics.py`

### Task 3: Rebuild the exact 30K snapshot and refresh audit artifacts

**Files:**
- Update output dir under: `data/lexicon/snapshots/`
- Update output dir under: `data/lexicon/audits/`

### Task 4: Refresh status/reporting docs with fresh evidence

**Files:**
- Modify: `docs/plans/2026-03-14-real-30k-curation-and-variant-enrichment-report.md`
- Modify: `docs/plans/2026-03-14-lexicon-30k-exhaustive-semantic-audit-notes.md`
- Modify: `docs/status/project-status.md`
