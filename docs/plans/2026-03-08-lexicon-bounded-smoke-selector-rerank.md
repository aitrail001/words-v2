# Lexicon Bounded Smoke, Selector Hardening, And LLM Rerank Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `smoke-openai-compatible` truly fast and bounded, continue improving deterministic learner-facing sense selection using the real 53-word sweep misses, add a grounded `llm-rerank` admin step that only returns selected `wn_synset_id`s and order, and provide a minimal comparison workflow between deterministic-only selection and deterministic-plus-rerank selection.

**Architecture:** Keep WordNet/wordfreq as the grounded lexical base. Treat deterministic selection as the primary selector. Add smoke-only bounds at the CLI/admin-tool layer rather than weakening the production selector globally. Add an optional rerank stage that reads a snapshot, considers bounded WordNet-backed candidate senses, asks the LLM to choose from those candidates only, writes a rerank artifact keyed by `lexeme_id`/`wn_synset_id`, and can be compiled or inspected alongside the deterministic selection for comparison.

**Tech Stack:** Python stdlib, existing lexicon CLI/enrichment pipeline, Node OpenAI-compatible transport, `unittest`, JSONL artifacts under snapshot directories.

---

### Task 1: Make smoke runs truly bounded

**Files:**
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Write failing tests**
- add parser/CLI tests for smoke-specific caps
- ensure smoke can limit senses-per-word and/or total enrichments without affecting normal `build-base`
- ensure payload reports bounded counts so operators can see what actually ran

**Step 2: Run targeted tests to verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_cli`
Expected: new smoke-bound tests fail before implementation.

**Step 3: Implement the smallest bounded smoke path**
- keep `build-base` behavior unchanged by default
- apply smoke-only caps after base selection and before enrichment
- preserve stable deterministic ordering while truncating for smoke
- surface cap metadata in smoke JSON output and operator docs

### Task 2: Harden deterministic selector using real sweep misses

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/wordnet_utils.py`
- Modify: `tools/lexicon/README.md`
- Modify: `docs/status/project-status.md`

**Step 1: Write failing regression tests**
- add focused ranking tests for representative real misses such as `direct`, `right`, `common`, `plain`, `check`, `charge`, and `scale`
- keep tests generic in spirit: everyday adjective/general-use senses should outrank obscure geographic/legal/sports/technical/tail senses where appropriate

**Step 2: Run targeted tests to verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base`
Expected: one or more new ranking regressions fail before heuristic tuning.

**Step 3: Implement minimal generic heuristic improvements**
- refine specialized/domain penalties and learner-value boosts
- avoid lemma-specific hardcoding
- keep the selector deterministic and WordNet-grounded

### Task 3: Add grounded LLM rerank admin step

**Files:**
- Create/Modify: `tools/lexicon/rerank.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/enrich.py` only if shared client helpers are reused
- Modify: `tools/lexicon/tests/test_cli.py`
- Create/Modify: `tools/lexicon/tests/test_rerank.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`

**Step 1: Write failing tests and schema expectations**
- add tests for a rerank payload constrained to provided candidates
- add tests that reject unknown or invented `wn_synset_id`s
- add tests for CLI command behavior and artifact writing

**Step 2: Implement a minimal rerank stage**
- input: bounded candidate senses from an existing snapshot (or direct candidate list helper)
- output: rerank artifact containing only `lexeme_id`, selected `wn_synset_id`s, and chosen order
- ensure the LLM cannot introduce unseen senses
- keep this stage optional and admin-only

### Task 4: Add deterministic-vs-rerank comparison flow

**Files:**
- Create/Modify: `tools/lexicon/compare_selection.py` or equivalent CLI-integrated helper
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Step 1: Add comparison tests**
- verify comparison can read deterministic snapshot selections and rerank artifact together
- verify comparison output highlights changes in selected IDs/order per lexeme

**Step 2: Implement minimal operator workflow**
- provide either a dedicated compare CLI or a narrow helper script exposed via CLI
- write comparison output as machine-readable JSON plus a concise CLI summary

### Task 5: Verify and record evidence

**Files:**
- Modify: `docs/status/project-status.md`

**Step 1: Run full verification**
Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: pass

Run: `PYTHONPYCACHEPREFIX=/tmp/lexicon-rerank-pycache python3 -m py_compile tools/lexicon/wordnet_utils.py tools/lexicon/build_base.py tools/lexicon/cli.py tools/lexicon/enrich.py tools/lexicon/rerank.py`
Expected: pass

**Step 2: Run representative local flows**
- run bounded smoke with tiny caps and verify fast output shape locally
- run a bounded deterministic selection snapshot
- run rerank on a tiny tricky-word sample if real gateway env is available; otherwise verify with mocked tests and report the gap honestly

**Step 3: Update canonical project status**
- summarize bounded smoke behavior, selector changes, rerank availability, comparison flow, and verification evidence in `docs/status/project-status.md`
