# Lexicon Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a separate offline lexicon tool that generates WordNet-backed, wordfreq-ranked, learner-enriched snapshot outputs and can import a compiled export into the local DB.

**Architecture:** The tool lives under `tools/lexicon/` as a Python CLI. It stores normalized snapshot files linked by stable IDs, validates them, then compiles a flattened `words.enriched.jsonl` export for explicit local DB import.

**Tech Stack:** Python 3.13, unittest/pytest-style targeted tests, NLTK WordNet, `wordfreq`, JSONL snapshot files, existing project Postgres/SQLAlchemy import integration.

---

## Next Approved Slice

Implement the approved next slice without changing the overall architecture:

1. wire real `WordNet` + `wordfreq` provider support into `build-base`
2. make operator-path `build-base` fail loudly when lexical dependencies are unavailable
3. add a separate `enrich` command that reads snapshot files and writes `enrichments.jsonl`
4. keep `compile-export` and `import-db` as separate later stages
5. keep test doubles/fakes for unit tests, but remove silent bootstrap fallback for actual CLI operator flow

---

### Task 1: Add provider-backed lexical base tests first

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Create: `tools/lexicon/tests/test_enrich.py`

**Step 1: Write failing tests for provider-backed build-base**

Cover:
- `build_base_records(...)` uses supplied rank and sense providers deterministically
- CLI `build-base --output-dir ...` writes snapshot files from real provider call plumbing
- CLI fails clearly when lexical providers are unavailable

**Step 2: Write failing tests for enrich flow**

Cover:
- `enrich` reads `senses.jsonl` and existing lexeme context from a snapshot dir
- `enrich` writes `enrichments.jsonl`
- CLI `enrich` command dispatches to the enrichment flow and emits JSON summary

**Step 3: Run targeted tests and confirm failure**

Run: `python3 -m unittest tools.lexicon.tests.test_build_base tools.lexicon.tests.test_cli tools.lexicon.tests.test_enrich`
Expected: FAIL

---

### Task 2: Add lexical provider modules and loud dependency failures

**Files:**
- Create: `tools/lexicon/wordnet_provider.py`
- Create: `tools/lexicon/wordfreq_provider.py`
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/cli.py`

**Step 1: Implement WordNet provider**

Add:
- lazy WordNet import/load helpers
- normalized sense extraction for a lemma
- clear dependency error when NLTK WordNet corpus is missing

**Step 2: Implement wordfreq provider**

Add:
- lazy `wordfreq` lookup helper
- rank normalization helper
- clear dependency error when package is missing

**Step 3: Wire build-base CLI to real providers**

Add:
- operator-path provider loading in CLI
- explicit failure path with human-readable errors
- keep direct function injection support for unit tests

**Step 4: Run targeted tests and confirm pass**

Run: `python3 -m unittest tools.lexicon.tests.test_build_base tools.lexicon.tests.test_cli`
Expected: PASS

---

### Task 3: Add enrichment service and CLI command

**Files:**
- Create: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/README.md`

**Step 1: Implement minimal offline enrichment flow**

Add:
- snapshot readers for lexemes/senses needed by enrichment
- injectable enrichment provider callable
- file writer for `enrichments.jsonl`
- summary payload including snapshot dir and count written

**Step 2: Add `enrich` CLI command**

Add:
- `enrich --snapshot-dir ...`
- optional metadata flags needed for provider bookkeeping, but no DB coupling
- CLI error handling consistent with other commands

**Step 3: Document operator workflow**

Document:
- `build-base -> enrich -> validate -> compile-export -> import-db`
- lexical dependency expectations
- current placeholder/injectable provider note for LLM enrichment if full external provider is not yet wired

**Step 4: Run targeted tests and confirm pass**

Run: `python3 -m unittest tools.lexicon.tests.test_enrich tools.lexicon.tests.test_cli`
Expected: PASS

---

### Task 4: Run verification and record status

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run focused lexicon suite**

Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: PASS

**Step 2: Run syntax sanity for touched Python files**

Run: `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m py_compile tools/lexicon/build_base.py tools/lexicon/wordnet_provider.py tools/lexicon/wordfreq_provider.py tools/lexicon/enrich.py tools/lexicon/cli.py`
Expected: PASS

**Step 3: Update canonical status board**

Add a 2026-03-07 entry for the provider-backed `build-base` and separate `enrich` command slice with exact evidence.

---

## Approved Follow-up Slice: OpenAI-Compatible P1 Schema Validation

Harden the real `openai_compatible` enrichment path only:

1. add strict tests first for `cefr_level`, `register`, list-of-strings fields, `forms`, and `confusable_words`
2. keep placeholder enrichment behavior unchanged
3. validate only the real endpoint payload before `EnrichmentRecord` creation
4. fail loudly with field-specific `RuntimeError` messages instead of silent coercion
5. verify with focused tests, full `tools/lexicon` suite, and `py_compile`

## Approved Follow-up Slice: Pytest Local + CI Support

Add operator-friendly pytest support for the lexicon tool without changing the underlying test suite design:

1. add `tools/lexicon/requirements-dev.txt` with pytest
2. document repo-local pytest usage for the lexicon venv
3. run lexicon tests in CI with `python -m pytest tools/lexicon/tests -q`
4. keep the existing offline smoke flow after tests
5. verify workflow YAML plus local repo-venv pytest execution

## Notes for Implementation

- Keep LLM credentials environment-driven only.
- Make snapshot output reproducible and versioned.
- Do not couple generation to app runtime requests.
- Prefer dry-run options for import commands.
- Keep custom expressions first-class from the beginning, even if the first implementation is minimal.
- Do not silently degrade operator-path lexical identity generation when required dependencies are missing.
