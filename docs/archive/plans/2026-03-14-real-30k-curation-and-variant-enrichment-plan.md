# Real 30K Curation And Variant Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add interim lexicalized-variant metadata for enrichment and generate a real post-collapse 30K deterministic common-word snapshot in a new dated directory.

**Architecture:** Extend `LexemeRecord` so `build-base` can emit variant metadata directly into `lexemes.jsonl`, then make the per-word enrichment prompt conditional on that metadata. Use the existing `build-base --top-words` production path inside a bounded outer loop to find the smallest `wordfreq` request window that yields exactly 30,000 surviving lexemes after deterministic canonicalization.

**Tech Stack:** Python 3.13, `tools/lexicon` CLI, JSONL snapshot artifacts, pytest, local shell tooling.

---

### Task 1: Add failing tests for variant metadata in interim lexeme rows

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/tests/test_models.py`

**Step 1: Write a failing build-base test**

Add a test that builds a lexicalized linked form such as `meeting` or `left` and asserts the resulting `LexemeRecord` contains:

- `is_variant_with_distinct_meanings=True`
- `variant_base_form=<base>`
- `variant_relationship='lexicalized_form'`

**Step 2: Write a failing model serialization test**

Add a `LexemeRecord` serialization test proving the new fields round-trip through `to_dict()` and constructor load.

**Step 3: Run only those tests and confirm they fail**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_models.py -q
```

Expected: failures for missing lexeme fields.

### Task 2: Implement variant metadata in the interim snapshot schema

**Files:**
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/build_base.py`

**Step 1: Extend `LexemeRecord`**

Add the new optional fields with safe defaults:

- `is_variant_with_distinct_meanings: bool = False`
- `variant_base_form: str | None = None`
- `variant_relationship: str | None = None`

**Step 2: Populate the fields in `build_base_records()`**

When a buildable canonical word has a linked base via deterministic canonicalization and remains its own headword, emit:

- `is_variant_with_distinct_meanings=True`
- `variant_base_form=<linked base>`
- `variant_relationship='lexicalized_form'`

Leave ordinary non-linked lexemes at default values.

**Step 3: Run the targeted tests and confirm they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_models.py -q
```

### Task 3: Add failing tests for variant-aware enrichment prompts

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write a failing prompt test**

Add a per-word prompt test for a variant-linked lexeme that asserts the prompt includes:

- the base word reference
- an instruction not to repeat ordinary meanings already covered by the base word
- an instruction to include only distinct/special meanings for the surface form
- an instruction to include a short note explaining it is another form of the base word

**Step 2: Run the prompt test and confirm it fails**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

Expected: missing prompt text failure.

### Task 4: Implement the variant-aware enrichment prompt

**Files:**
- Modify: `tools/lexicon/enrich.py`

**Step 1: Add a small helper for variant-specific prompt instructions**

Generate the extra instruction block only when `lexeme.is_variant_with_distinct_meanings` is true and `variant_base_form` is present.

**Step 2: Apply the helper to both the normal prompt and repair prompt**

Keep behavior unchanged for ordinary lexemes.

**Step 3: Run enrichment tests and confirm they pass**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
```

### Task 5: Run full lexicon verification

**Files:**
- No code changes expected

**Step 1: Run the full lexicon suite**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

Expected: all tests pass.

### Task 6: Produce the real deterministic 30K snapshot

**Files:**
- Create: `data/lexicon/snapshots/words-30000-20260314-main-real/*`

**Step 1: Write a small bounded search script or shell loop**

Use the existing CLI:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m tools.lexicon.cli build-base --top-words N --rerun-existing --output-dir data/lexicon/snapshots/words-30000-20260314-main-real
```

Search for the smallest `N` whose resulting `lexeme_count` is exactly `30000`.

**Step 2: Preserve the final snapshot**

Keep the final dated snapshot directory intact for later LLM enrichment.

**Step 3: Record the chosen request window and final counts**

Capture:

- requested top-word window
- final `lexeme_count`
- `sense_count`
- `ambiguous_form_count`

### Task 7: Document the result and update live status

**Files:**
- Create: `docs/plans/2026-03-14-real-30k-curation-and-variant-enrichment-report.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write the tracked report**

Document:

- the schema/prompt change
- verification evidence
- the final top-word request window needed to obtain the real 30K post-collapse list
- the output snapshot path

**Step 2: Update project status**

Add a concise status entry with fresh evidence and the new dated 30K snapshot artifact path.

### Task 8: Final verification before completion

**Files:**
- No additional code changes expected

**Step 1: Re-run the exact verification set used for the completion claim**

Run:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
```

And keep the final successful 30K `build-base` command output for evidence.
