# Lexicon Benchmarks And Tooling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Document the lexicon model benchmark thoroughly, patch the lexicon tool with benchmark-friendly real-provider controls, and continue improving learner-facing sense selection quality for broad mixed-POS words.

**Architecture:** Keep benchmark documentation operator-facing under `tools/lexicon/`, summarize the decision in `docs/status/project-status.md`, then add first-class model/reasoning controls to the real enrichment path without changing the offline/admin pipeline shape. After documentation and tooling controls land, improve sense selection via tests-first heuristic tuning for remaining quality failures like `break` and weak adjective choices such as `open`.

**Tech Stack:** Python stdlib, existing lexicon CLI/enrichment pipeline, Node OpenAI-compatible transport, `unittest`, local benchmark artifacts.

---

### Task 1: Document the benchmark thoroughly

**Files:**
- Create: `tools/lexicon/MODEL_BENCHMARKS.md`
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/README.md` (short pointer only if needed)

**Step 1: Write the benchmark doc**
- document gateway assumptions, low-effort setting, prompt construction method, and exact target sets
- capture both benchmark scopes: 4-prompt and 14-prompt runs
- summarize quality ranking, latency ranking, and 20k-word runtime projections
- clearly separate enrichment-model quality from upstream sense-selection quality
- include artifact locations under `/tmp` as reproducibility evidence

**Step 2: Add concise status entry**
- summarize benchmark outcome in `docs/status/project-status.md`
- link the detailed interpretation to the new operator-facing benchmark doc

### Task 2: Patch benchmark-friendly tool controls

**Files:**
- Modify: `tools/lexicon/config.py`
- Modify: `tools/lexicon/enrich.py`
- Modify: `tools/lexicon/cli.py`
- Modify: `tools/lexicon/node/openai_compatible_responses.mjs`
- Modify: `tools/lexicon/tests/test_config.py`
- Modify: `tools/lexicon/tests/test_enrich.py`
- Modify: `tools/lexicon/tests/test_cli.py`
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/.env.example` (if new env is exposed)

**Step 1: Write failing tests**
- add config tests for an optional reasoning-effort env value
- add enrich tests proving the real provider forwards reasoning effort to the node transport and/or HTTP payload
- add CLI tests for model override / reasoning override flags if exposed there

**Step 2: Run targeted tests to verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_config tools.lexicon.tests.test_enrich tools.lexicon.tests.test_cli`
Expected: one or more new tests fail before implementation.

**Step 3: Implement minimal controls**
- add `LEXICON_LLM_REASONING_EFFORT` support with conservative validation
- support passing model override and reasoning effort through the enrichment builder/runner path
- preserve current defaults when the new setting is absent

### Task 3: Improve remaining sense-selection quality

**Files:**
- Modify: `tools/lexicon/tests/test_build_base.py`
- Modify: `tools/lexicon/wordnet_utils.py`
- Modify: `tools/lexicon/README.md`
- Modify: `docs/status/project-status.md`

**Step 1: Add failing quality tests**
- add a focused regression test for `break`-like broad verbs so low-value obedience/control senses do not outrank more core learner senses
- add a focused regression test for `open`-like adjectives so stronger everyday adjective senses beat narrower body-part-only senses when both exist

**Step 2: Run targeted tests to verify RED**
Run: `python3 -m unittest tools.lexicon.tests.test_build_base`
Expected: the new quality tests fail before heuristic tuning.

**Step 3: Implement minimal heuristic changes**
- refine specialized/learner-value penalties for `break`-like and `open`-like cases without lemma-specific hardcoding
- keep the new POS-viability layer soft and deterministic

### Task 4: Verify and record evidence

**Files:**
- Modify: `docs/status/project-status.md`
- Modify: `tools/lexicon/MODEL_BENCHMARKS.md` only if final evidence text needs refresh

**Step 1: Run full verification**
Run: `python3 -m unittest discover -s tools/lexicon/tests -p 'test_*.py'`
Expected: pass

Run: `PYTHONPYCACHEPREFIX=/tmp/lexicon-ranking-pycache python3 -m py_compile tools/lexicon/wordnet_utils.py tools/lexicon/wordnet_provider.py tools/lexicon/build_base.py tools/lexicon/cli.py tools/lexicon/enrich.py tools/lexicon/config.py`
Expected: pass

**Step 2: Run representative real smoke**
- rerun a small real `smoke-openai-compatible` flow with the new controls enabled
- inspect outputs for both model metadata and learner-facing JSON validity

**Step 3: Report remaining gaps honestly**
- explicitly note any still-imperfect sense cases after the final heuristic pass
