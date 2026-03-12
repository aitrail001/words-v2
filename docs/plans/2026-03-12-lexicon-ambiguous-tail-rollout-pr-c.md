# Lexicon Ambiguous-Tail Rollout PR C Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ambiguous-form adjudication operationally safe for larger lexicon rollouts by deferring unresolved ambiguous forms from base outputs, exposing that state to operators, and validating the related sidecar artifacts.

**Architecture:** Keep the existing deterministic canonicalization plus optional adjudication model, but stop treating unresolved `unknown_needs_llm` forms as publishable base lexemes. Preserve them in `canonical_variants.jsonl` and `ambiguous_forms.jsonl`, expose their pending status in lookup/status commands, and have snapshot validation catch inconsistent sidecars.

**Tech Stack:** Python 3.13, existing lexicon CLI, JSONL artifacts, pytest.

---

### Task 1: Add failing tests for deferred ambiguous forms

**Files:**
- Modify: `tools/lexicon/tests/test_form_adjudication.py`
- Modify: `tools/lexicon/tests/test_cli_canonical_registry.py`
- Modify: `tools/lexicon/tests/test_validate.py`

**Steps:**
1. Add a test proving unresolved ambiguous forms stay out of `lexemes`/`senses` until adjudicated.
2. Add a status/lookup test proving operators can see pending adjudication details.
3. Add a validation test that flags unresolved ambiguous forms if they leak into `lexemes.jsonl`.
4. Run targeted tests and confirm failure.

### Task 2: Defer unresolved ambiguous forms from base outputs

**Files:**
- Modify: `tools/lexicon/build_base.py`

**Steps:**
1. Keep writing `canonical_variants.jsonl` and `ambiguous_forms.jsonl` for unresolved forms.
2. Skip unresolved `unknown_needs_llm` forms when building `lexemes`, `senses`, `concepts`, `canonical_entries`, and built generation-status rows.
3. Preserve current adjudicated and deterministic non-ambiguous flows.

### Task 3: Surface adjudication state in lookup/status

**Files:**
- Modify: `tools/lexicon/canonical_registry.py`
- Modify: `tools/lexicon/cli.py` only if payload plumbing is needed

**Steps:**
1. Prefer direct canonical entries before variant shadow matches.
2. Load `ambiguous_forms.jsonl` and expose pending adjudication metadata.
3. Make `status-entry` report `needs_adjudication`, `ambiguity_reason`, and `candidate_forms` even when `base_built` is false.

### Task 4: Validate ambiguous sidecars

**Files:**
- Modify: `tools/lexicon/validate.py`

**Steps:**
1. Parse `canonical_variants.jsonl` and `ambiguous_forms.jsonl` when present.
2. Validate ambiguous rows structurally.
3. Flag unresolved ambiguous surface forms that incorrectly appear in built `lexemes.jsonl`.
4. Flag ambiguous rows missing a matching `needs_llm_adjudication` variant record.

### Task 5: Update docs and status

**Files:**
- Modify: `tools/lexicon/README.md`
- Modify: `tools/lexicon/OPERATOR_GUIDE.md`
- Modify: `docs/status/project-status.md`

**Steps:**
1. Document the deterministic-only vs adjudication operator policy.
2. Document that unresolved ambiguous forms are now deferred, not built.
3. Record verification evidence and the rollout recommendation.

### Task 6: Verify, commit, PR, merge, clean up

**Verification:**
- Targeted form-adjudication / registry / validate tests
- Full lexicon suite
- Small CLI smoke covering deferred ambiguous lookup/status flow
- Fresh diff review before commit
