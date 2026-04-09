# Lexicon 30K Exhaustive Semantic Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Audit the entire deterministic 30K lexeme set plus near-boundary candidates, manually review suspicious lexical forms, and move lexeme-specific canonicalization fixes into tracked datasets without overcomplicating the core deterministic rules.

**Architecture:** Generate a full audit inventory for every lexeme in the dated 30K snapshot and a boundary-band inventory for replacement candidates, derive suspicious buckets with deterministic heuristics, manually classify current misclassifications, update the tracked anomaly and irregular-form datasets where appropriate, and rebuild the snapshot to confirm the final audited 30K remains exact and stable.

**Tech Stack:** Python 3.13, `tools/lexicon` snapshot JSONL artifacts, tracked anomaly JSON, pytest, local shell tooling, parallel subagents for independent bucket review.

---

### Task 1: Build the full 30K audit inventory

**Files:**
- Create: `tools/lexicon/audit_30k_semantics.py`
- Create: `data/lexicon/audits/words-30000-20260314-main-real.audit.json`
- Create: `data/lexicon/audits/words-30000-20260314-main-real.audit.summary.json`
- Create: `docs/plans/2026-03-14-lexicon-30k-exhaustive-semantic-audit-notes.md`

**Steps:**
1. Load the final dated snapshot inputs (`lexemes.jsonl`, `canonical_variants.jsonl`, `canonical_entries.jsonl`).
2. Load enough near-boundary source inventory to inspect words that could enter the 30K after additional collapses.
3. Emit one audit row per lexeme with enough metadata to support semantic review.
4. Add deterministic risk buckets for suspicious classes, especially irregular forms and suffix-based collapses.
5. Write the audit artifacts and review notes so all 30,000 lexemes plus the inspected boundary band are covered.

### Task 2: Review suspicious buckets and classify dataset actions

**Files:**
- Modify: `docs/plans/2026-03-14-lexicon-30k-exhaustive-semantic-audit-notes.md`

**Steps:**
1. Extract the suspicious lexemes from the audit inventory.
2. Split suspicious buckets into independent review groups, including irregular noun/adjective forms, irregular verb forms, and suffix-risk tails.
3. Manually classify each suspicious word as:
   - accept current deterministic outcome
   - add `force_keep_separate`
   - add `force_collapse_to_canonical`
   - add irregular non-verb mapping
   - add irregular verb-form mapping
4. Record the reasoning in tracked notes.

### Task 3: Add failing regression tests from audited misclassifications

**Files:**
- Test: `tools/lexicon/tests/test_canonical_forms.py`

**Steps:**
1. Add test coverage for representative audited misses such as irregular plural, irregular comparative/superlative, irregular verb-form, and false suffix-collapse cases.
2. Run the targeted tests to confirm they fail for the current behavior.

### Task 4: Update tracked datasets and deterministic lookups

**Files:**
- Create: `tools/lexicon/data/irregular_form_overrides.json`
- Create: `tools/lexicon/data/irregular_verb_forms.json`
- Modify: `tools/lexicon/data/canonical_anomalies.json`
- Modify: `tools/lexicon/canonical_forms.py`
- Test: `tools/lexicon/tests/test_canonical_forms.py`

**Steps:**
1. Add new dataset rows only for clearly bounded lexical knowledge.
2. Update canonicalization logic to consult irregular datasets before generic suffix heuristics.
3. Preserve keep-both-linked or keep-separate outcomes for lexicalized forms with distinct meanings.
4. Re-run targeted canonicalization tests.

### Task 5: Rebuild and verify the audited 30K snapshot

**Files:**
- Modify: `data/lexicon/snapshots/words-30000-20260314-main-real/*`

**Steps:**
1. Rebuild the dated snapshot against the updated anomaly list.
2. Confirm exact row counts and zero ambiguous rows.
3. Re-audit the previously suspicious words and any newly admitted boundary words to confirm the intended outcomes hold.

### Task 6: Report the exhaustive audit results

**Files:**
- Modify: `docs/plans/2026-03-14-real-30k-curation-and-variant-enrichment-report.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Summarize audit coverage, suspicious-bucket counts, and added tracked dataset entries.
2. Record the final audited 30K counts, boundary-band effects, and remaining residual risks, if any.
3. Preserve explicit evidence for the later PR.
