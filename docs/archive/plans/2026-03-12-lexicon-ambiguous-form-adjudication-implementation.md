# 2026-03-12 — Lexicon ambiguous-form adjudication PR 3 implementation

## Scope

Implement PR 3 of the lexicon roadmap: an optional, bounded LLM adjudication step for ambiguous canonicalization outcomes.

## Agreed constraints

1. Deterministic canonicalization remains the default path.
2. The LLM may only choose among bounded deterministic candidates or keep the surface form.
3. The LLM must not invent new lemmas or freeform canonical targets.
4. Adjudication must be optional, auditable, and replayable from artifacts.
5. This PR should not change the PR 1 / PR 2 happy path unless operators explicitly supply adjudication overrides.

## Design

### Deterministic ambiguity detection

Extend canonicalization output with richer ambiguity metadata:
- bounded `candidate_forms`
- `ambiguity_reason`
- `needs_llm_adjudication`

Ambiguous cases are those where:
- a non-trivial candidate set exists,
- no deterministic candidate clears the collapse threshold,
- and the decision is not an obvious `keep_both_linked` lexicalized case.

### Artifacts

Add optional adjudication artifacts:
- `ambiguous_forms.jsonl`
- `form_adjudications.jsonl`

`ambiguous_forms.jsonl` rows should include:
- `surface_form`
- `deterministic_decision`
- `canonical_form`
- `linked_canonical_form`
- `candidate_forms`
- `decision_reason`
- `confidence`
- `wordfreq_rank`
- `sense_labels`
- `ambiguity_reason`

`form_adjudications.jsonl` rows should include:
- `surface_form`
- `selected_action` (`collapse_to_canonical|keep_separate|keep_both_linked`)
- `selected_canonical_form`
- `selected_linked_canonical_form`
- `candidate_forms`
- `model_name`
- `prompt_version`
- `generation_run_id`
- `confidence`
- `adjudication_reason`

### CLI

Add:
- `detect-ambiguous-forms --words ... --output ...`
- `adjudicate-forms --input ambiguous_forms.jsonl --output form_adjudications.jsonl --provider-mode ...`
- `build-base --adjudications form_adjudications.jsonl ...`

`build-base --adjudications ...` should apply only exact `surface_form` overrides and keep everything else deterministic.

### LLM contract

Prompt must include:
- surface form
- bounded candidate forms
- short evidence summary
- strict output schema

Allowed outputs only:
- `selected_action`
- `selected_canonical_form`
- `selected_linked_canonical_form`
- `adjudication_reason`
- `confidence`

Validation rules:
- `selected_action` must be one of the allowed actions
- `selected_canonical_form` must be either the surface form or one of `candidate_forms`
- `selected_linked_canonical_form` must be null or one of `candidate_forms`
- no extra invented candidates allowed

## Verification

1. Unit tests for ambiguity detection and candidate emission.
2. Unit tests for bounded adjudication payload validation.
3. CLI tests for `detect-ambiguous-forms` and `build-base --adjudications`.
4. Build-base override tests proving adjudications can change the final canonical word set.

## Expected non-goals

1. No backend/admin API work in this PR.
2. No automatic adjudication in the default operator flow.
3. No human-review UI in this slice.
