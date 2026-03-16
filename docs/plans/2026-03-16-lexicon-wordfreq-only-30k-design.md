# Lexicon Wordfreq-Only 30K Design

Date: 2026-03-16
Owner: Codex

## Goal

Replace the current WordNet-constrained 30K lexicon enrichment pipeline with a simpler `wordfreq + LLM` pipeline that:

- uses `wordfreq` only to source candidate words
- excludes obviously low-value inventory items such as alphabet rows and weak function-token admissions
- asks the LLM to decide whether a candidate should be:
  - discarded
  - kept as a normal word entry
  - kept as a derived-form entry with its own special meanings
- continues enrichment until a final learner-useful 30K words are accepted

## Why Replace The Current Design

The current pipeline still depends on WordNet in important ways even in `word_only` mode:

- `build-base` uses WordNet to construct sense candidates
- enrichment still sends WordNet-derived `sense_id` constraints
- validation failures now come from duplicated or invalid `sense_id` selection

That architecture adds complexity the user no longer wants:

- WordNet sense grounding
- deterministic base-form and distinct-variant adjudication
- constrained `sense_id` output validation

The desired product behavior is simpler:

- decide usefulness from the word itself
- keep only learner-useful standalone entries
- if a word is only an inflectional/derived form with no extra meaning, discard it
- if a word is a derived form with special lexicalized meanings, keep it and focus only on those meanings plus one simple link back to the base word

## Core Product Rules

For each candidate word, the model should decide exactly one of:

1. `discard`
2. `keep_standard`
3. `keep_derived_special`

### `discard`

Use when:

- the row is not a useful standalone learner word
- the row is just alphabet or inventory noise
- the row is only a plain inflectional/derived form of another word with no special lexicalized meaning worth teaching separately

Examples of things that should generally be discarded:

- alphabet entries like `a` through `z` when they are only letter names
- weak admissions like `an`
- plain inflectional variants whose meaning is fully covered by the base word

### `keep_standard`

Use when:

- the word is a useful standalone learner entry
- the word should receive normal learner-facing meanings, examples, translations, and relations

### `keep_derived_special`

Use when:

- the word is related to a base form
- but it also has its own lexicalized or otherwise special meanings worth teaching separately

For these rows, the model should:

- include one simple meaning or note linking it to the base word
- avoid repeating ordinary base-word meanings
- focus the rest of the entry on the special meanings that justify keeping the surface word

## Architectural Shift

### Old model

- deterministic canonicalization and WordNet-based sense selection first
- LLM enriches only preselected grounded senses

### New model

- `wordfreq` inventory first
- bounded deterministic prefilter only for obvious junk exclusions
- LLM decides:
  - discard vs keep
  - standard vs derived-special
  - learner-facing meanings directly

This removes the current `sense_id`-based contract from the enrichment stage.

## Proposed Pipeline

1. Build a ranked candidate inventory from `wordfreq`
2. Apply a narrow deterministic exclusion list for obviously non-useful admissions
3. Run LLM enrichment on candidates in order
4. For each candidate, accept only rows whose final decision is `keep_standard` or `keep_derived_special`
5. Continue down the ranked inventory until `30000` accepted entries exist
6. Compile and import the accepted entries into the DB

## Deterministic Logic We Keep

We should not remove all deterministic logic.

Keep:

- `wordfreq` inventory and ranking
- explicit bounded exclusion datasets for things we know we do not want
- operational checkpoint/resume/durability behavior
- entity-category tagging if it still improves prompting

Remove or greatly reduce:

- WordNet sense selection as an enrichment prerequisite
- deterministic base-word adjudication as a hard gate
- current `sense_id` validation contract

## New LLM Contract

The prompt should send only:

- the surface word
- its `wordfreq` rank
- optional entity category if already known
- clear instructions for `discard` vs `keep_standard` vs `keep_derived_special`

The response should return:

- a decision field
- optional base-word link when `keep_derived_special`
- learner-facing meanings and examples directly
- required translations

No WordNet `sense_id` fields should be involved.

## Acceptance Counting

The final 30K list should count only accepted entries:

- `keep_standard`
- `keep_derived_special`

Discarded rows do not count toward the 30K target. The system should continue walking further down the ranked `wordfreq` inventory until `30000` accepted entries exist.

## Artifact Strategy

Keep the artifact-first model under `data/lexicon/snapshots/...`.

The new run should still preserve:

- candidate inventory inputs
- per-candidate decision outputs
- accepted-entry compiled export
- checkpoint and failure sidecars

This remains the canonical source of truth even if DB preview imports continue during the run.

## Migration Plan

The current live WordNet-constrained 30K run should be stopped and preserved only as a historical experiment snapshot.

Do not continue burning API time on a pipeline that is being replaced.

The new implementation should be built and validated first, then a fresh 30K run should start under a new dated snapshot directory.

## Success Criteria

This redesign is successful if:

1. The tool no longer requires WordNet for the 30K enrichment path
2. The LLM can discard non-useful words directly
3. Derived-form entries are kept only when they have special learner-useful meanings
4. The final accepted entry count reaches exactly `30000`
5. The artifact-first, resumable, preview-importable rollout model remains intact
