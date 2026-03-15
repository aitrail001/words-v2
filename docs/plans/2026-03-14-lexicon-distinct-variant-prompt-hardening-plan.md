# Lexicon Distinct-Variant Prompt Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit-plus-inferred distinct-derived-entry metadata so later lexicon enrichment prompts link those words to their base forms and generate only their standalone meanings, while preserving entity-category-aware prompting.

**Architecture:** Introduce a tracked dataset for audited distinct-derived entries, add bounded fallback inference in the deterministic lexicon policy path, carry the resulting metadata into `LexemeRecord`, and harden the per-word prompt to use that metadata in both normal and repair prompts.

**Tech Stack:** Python 3.13, `tools/lexicon`, JSON policy data, pytest.

---

### Task 1: Add failing tests for explicit distinct-derived metadata

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/tests/test_models.py`

**Step 1: Write a failing build-base test**

Add a test that uses an explicit dataset-backed word like `building` and asserts the resulting lexeme row carries:

- `is_variant_with_distinct_meanings=True`
- `variant_base_form='build'`
- a stable relationship label for the derived variant

**Step 2: Write a failing model serialization test**

Assert the new metadata fields round-trip through `LexemeRecord.to_dict()` and constructor reload.

**Step 3: Run the targeted tests and confirm they fail**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_models.py -q
```

### Task 2: Add failing tests for inference fallback

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/tests/test_canonical_forms.py`

**Step 1: Write a failing inference test**

Add a case where no explicit dataset row exists but a derived form is conservative to infer as its own linked entry based on the bounded inference rules.

**Step 2: Add a guardrail test**

Add a negative test proving the inference does not fire for an ordinary inflectional form that should remain plain.

**Step 3: Run the targeted tests and confirm they fail**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_canonical_forms.py -q
```

### Task 3: Implement the tracked dataset and inference path

**Files:**
- Create: `tools/lexicon/data/distinct_variant_entries.json`
- Modify: `tools/lexicon/policy_data.py`
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/canonical_forms.py` if needed for bounded inference inputs

**Step 1: Add the dataset**

Create a tracked JSON file containing audited `surface -> base` rows plus metadata like `relationship`, `reason`, and optional prompt note.

**Step 2: Add policy loaders**

Load and normalize the dataset in `policy_data.py`.

**Step 3: Add bounded fallback inference**

Implement a conservative inference helper for uncovered cases.

**Step 4: Carry the metadata into lexeme rows**

Ensure the lexeme output records enough detail for later prompt guidance.

**Step 5: Run the targeted tests and confirm they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_models.py tools/lexicon/tests/test_canonical_forms.py -q
```

### Task 4: Add failing tests for prompt hardening

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write a failing prompt test for distinct-derived entries**

Assert that the prompt for a `building`-style lexeme:

- references the base word
- forbids duplicating ordinary base-word meanings
- asks only for the standalone meanings/usages of the derived word
- requires a short note linking the word back to the base

**Step 2: Keep entity-category coverage**

Assert category guidance still appears for a place/name/brand-style lexeme.

**Step 3: Run the prompt tests and confirm they fail**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 5: Implement prompt hardening

**Files:**
- Modify: `tools/lexicon/enrich.py`

**Step 1: Update the variant prompt helper**

Make the prompt guidance specific to distinct-derived entries and include any extra note carried from the dataset/inference path.

**Step 2: Apply it to normal and repair prompts**

Keep ordinary words unchanged.

**Step 3: Run enrichment tests and confirm they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 6: Run the full lexicon suite

**Files:**
- No additional code changes expected

**Step 1: Run the full test suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

### Task 7: Refresh live status if behavior scope changed

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Update the lexicon workstream summary**

If the prompt/metadata behavior meaningfully changes the live lexicon state, add concise evidence-backed wording to the status board.

### Task 8: Final verification before completion

**Files:**
- No additional code changes expected

**Step 1: Re-run the exact verification set used for the completion claim**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```
