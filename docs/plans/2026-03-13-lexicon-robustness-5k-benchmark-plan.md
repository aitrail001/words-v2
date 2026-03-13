# Lexicon Robustness 5K Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate and run a deterministic 5K-word robustness benchmark that mixes all major boundary classes, then assess whether the non-LLM `build-base` path is ready to scale toward the 30K rollout.

**Architecture:** Build one mixed benchmark from existing benchmark buckets plus fresh edge-case sources so the final list reflects both realistic common-word traffic and known deterministic failure modes. Run only `build-base`, analyze canonical decisions and ambiguous tails, and produce a tracked report with explicit readiness judgment and residual risk classes.

**Tech Stack:** Python 3.13, `tools/lexicon` CLI/build-base pipeline, JSON/JSONL benchmark artifacts, pytest, local shell tooling.

---

### Task 1: Define the mixed robustness benchmark composition

**Files:**
- Create: `docs/plans/2026-03-13-lexicon-robustness-5k-benchmark-design.md`
- Modify: `docs/plans/2026-03-13-lexicon-robustness-5k-benchmark-plan.md`

**Steps:**
1. Enumerate the source classes to mix into the 5K benchmark: common rollout words, morphology-heavy words, semantic-neighbor words, suffix-risk words, short-stem words, proper names/surnames, currencies/units, invariant plurals, and lexicalized derivatives.
2. Define a deterministic target allocation for each class so the final set is diverse but still weighted toward realistic common words.
3. Record the benchmark design and success criteria in a short design note.

### Task 2: Generate the 5K benchmark artifacts

**Files:**
- Create: `data/lexicon/benchmarks/robustness_border_5000_20260313.txt`
- Create: `data/lexicon/benchmarks/robustness_border_5000_20260313.json`
- Create: `data/lexicon/benchmarks/robustness_border_5000_20260313.summary.json`

**Steps:**
1. Reuse existing benchmark lists where possible instead of inventing new words from scratch.
2. Add fresh deterministic seed sources for boundary classes not fully covered by the existing six benchmark buckets.
3. Ensure the final word list is normalized, deduplicated, and deterministic.
4. Save machine-readable metadata describing source mix and counts.

### Task 3: Run deterministic build-base on the 5K list

**Files:**
- Create: `data/lexicon/snapshots/robustness-border-5000-20260313/*`

**Steps:**
1. Run `tools.lexicon.cli build-base --rerun-existing` against the 5K list with no LLM/adjudication.
2. Capture timing, decision counts, ambiguous-tail counts, and lexeme/sense totals.
3. Preserve the snapshot artifacts for direct inspection.

### Task 4: Analyze robustness outcomes and residual risks

**Files:**
- Create: `docs/plans/2026-03-13-lexicon-robustness-5k-benchmark-report.md`

**Steps:**
1. Inspect `canonical_variants.jsonl` and `ambiguous_forms.jsonl` for suspicious selected links and suspicious candidate tails.
2. Check representative positive probes to confirm valid morphology still works.
3. Summarize the main residual deterministic risk classes, especially anything likely to blow up at 30K scale.
4. Write an explicit readiness judgment: ready, mostly ready with bounded tails, or not ready.

### Task 5: Update live status and verify

**Files:**
- Modify: `docs/status/project-status.md`

**Steps:**
1. Add a status entry summarizing the 5K benchmark result and the 30K-readiness judgment.
2. Run at least the relevant lexicon test scope plus the real 5K benchmark command used for evidence.
3. Report what was verified and any residual gaps.
