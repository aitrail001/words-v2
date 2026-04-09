# Lexicon Wordfreq-Only 30K Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current WordNet-grounded lexicon enrichment path with a `wordfreq + LLM` pipeline that accepts `30000` learner-useful words by LLM decision alone while preserving resumable snapshot artifacts and DB preview import.

**Architecture:** Keep `wordfreq` as the inventory source and retain artifact-first snapshot operations, but remove WordNet sense grounding from the enrichment contract. The enrichment stage will produce a per-word decision (`discard`, `keep_standard`, `keep_derived_special`) plus learner-facing senses directly; compilation and DB import will consume accepted word entries rather than WordNet-backed `sense_id` records.

**Tech Stack:** Python CLI tooling, JSONL snapshot artifacts, OpenAI-compatible Responses API transport, SQLAlchemy-backed DB import, pytest.

---

### Task 1: Freeze the contract in tests

**Files:**
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_compile_export.py`
- Modify: `tools/lexicon/tests/test_import_db.py`
- Modify: `tools/lexicon/tests/test_cli.py`

**Step 1: Write failing enrichment tests for the new decision contract**

Add tests that assert:
- `word_only` enrichment payload no longer requires or validates `sense_id`
- decision values are limited to `discard`, `keep_standard`, `keep_derived_special`
- `discard` rows produce no compiled word
- `keep_derived_special` requires a base-word link note and keeps only special meanings plus a simple base-word reference sense

**Step 2: Run the focused tests to verify they fail**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`

Expected: failures referencing the old `sense_id` / WordNet-shaped contract.

**Step 3: Add fixture coverage for accepted-count progression**

Add tests that prove:
- the enrichment loop continues until `N` accepted rows exist, not merely `N` attempted rows
- checkpoint and completion sidecars can be resumed without losing already accepted entries
- ordered flush logic still preserves deterministic final outputs

**Step 4: Re-run focused tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_import_db.py tools/lexicon/tests/test_cli.py -q`

Expected: new tests fail for the intended contract gaps only.

### Task 2: Introduce word-only data models

**Files:**
- Modify: `tools/lexicon/models.py`
- Modify: `tools/lexicon/json_schemas.py` if present, otherwise keep schema helpers in `tools/lexicon/enrich.py`
- Test: `tools/lexicon/tests/test_enrich.py`

**Step 1: Add minimal accepted-entry model fields**

Introduce upstream records that can represent:
- candidate decision
- optional rejection reason
- optional `base_word`
- accepted senses without `sense_id`
- prompt metadata needed for later import/audit

Prefer extending the existing record layer conservatively rather than rewriting everything at once.

**Step 2: Keep compiled export compatibility in mind**

Preserve the downstream `CompiledWordRecord` shape as far as possible so the DB import path remains a small adaptation instead of a full rewrite.

**Step 3: Run focused model/enrichment tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q`

Expected: model serialization tests pass or expose only the next missing implementation edge.

### Task 3: Remove WordNet from the enrichment request path

**Files:**
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Test: `tools/lexicon/tests/test_enrich.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Replace the prompt/schema contract**

Update the enrichment prompt so it sends only:
- surface word
- wordfreq rank
- optional entity category
- explicit instructions for `discard`, `keep_standard`, `keep_derived_special`

The response schema should require only the new decision contract and learner-facing senses.

**Step 2: Remove `sense_id`-based validation on the new path**

Validation should instead ensure:
- legal decision value
- accepted rows contain at least one learner sense
- derived-special rows include a base-word reference and do not duplicate generic base-form coverage structurally

**Step 3: Keep robust transport behavior**

Retain:
- retry on transient parse/transport failures
- checkpoint sidecars
- periodic flush to disk
- bounded `--max-new-completed-lexemes`

**Step 4: Run focused enrichment/CLI tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_cli.py -q`

Expected: passing tests for the new schema, retries, checkpointing, and CLI options.

### Task 4: Simplify inventory build and acceptance counting

**Files:**
- Modify: `tools/lexicon/build_base.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/policy_data.py`
- Modify: `tools/lexicon/data/*.json`
- Test: `tools/lexicon/tests/test_build_base.py`
- Test: `tools/lexicon/tests/test_cli.py`

**Step 1: Keep only bounded deterministic filtering**

Preserve:
- `wordfreq` ranking
- explicit tail-exclusion datasets
- optional entity-category datasets

Stop using WordNet-backed sense construction as a prerequisite for the 30K rollout path.

**Step 2: Ensure inventory walks until accepted count is satisfied**

The tool should:
- keep attempting candidates in rank order
- skip discarded rows cleanly
- stop only when `target_accepted_words == 30000`

**Step 3: Run focused build tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_cli.py -q`

Expected: inventory tests pass with the new candidate source and stopping rule.

### Task 5: Rework compile/export and DB import for accepted word entries

**Files:**
- Modify: `tools/lexicon/compile_export.py`
- Modify: `tools/lexicon/import_db.py`
- Modify: `tools/lexicon/tests/test_compile_export.py`
- Modify: `tools/lexicon/tests/test_import_db.py`

**Step 1: Compile directly from accepted word enrichments**

Compilation should:
- ignore discarded rows
- transform accepted word-level senses into `CompiledWordRecord`
- preserve metadata such as `entry_id`, `entity_category`, provenance, prompt version, and generated timestamps

**Step 2: Keep import idempotence**

The DB import path should continue to:
- upsert words
- replace/update meanings, examples, relations, and translations
- attach enrichment job/run metadata

But it should not depend on WordNet `sense_id`.

**Step 3: Run focused compile/import tests**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_import_db.py -q`

Expected: passing compile/import coverage for standard and derived-special entries.

### Task 6: Verify the rollout contract and refresh documentation

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/plans/2026-03-16-lexicon-wordfreq-only-30k-design.md`

**Step 1: Run the targeted lexicon suite**

Run: `/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_cli.py tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_enrich.py tools/lexicon/tests/test_import_db.py -q`

Expected: green targeted suite.

**Step 2: Run one end-to-end dry snapshot without live LLM calls if fixtures allow**

Use fixture-backed or stubbed enrichment to prove:
- accepted count handling
- sidecar growth
- compile output generation
- import compatibility

**Step 3: Update live status**

Record:
- the old WordNet 30K rollout as superseded
- the new pipeline status and evidence
- remaining rollout risks, if any

**Step 4: Commit**

```bash
git add docs/status/project-status.md tools/lexicon docs/plans/2026-03-16-lexicon-wordfreq-only-30k-design.md docs/plans/2026-03-16-lexicon-wordfreq-only-30k-plan.md
git commit -m "feat: redesign lexicon 30k enrichment around wordfreq-only LLM decisions"
```
