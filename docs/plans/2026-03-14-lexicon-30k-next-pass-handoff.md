# Lexicon 30K Next Pass Handoff

Date: 2026-03-14
Owner: Codex
Branch: `curate_real_30k_20260314`
Worktree: `/Users/johnson/AI/src/words-v2/.worktrees/curate_real_30k_20260314`

## Current Verified State

The deterministic irregular/variant hardening pass is complete for the current scope.

Current exact deterministic 30K snapshot:

- `data/lexicon/snapshots/words-30000-20260314-main-real-boundary-hardened`

Exact request boundary:

- `39423 -> 29999`
- `39424 -> 30000`
- `39426 -> 30001`

Verified counts:

- `lexeme_count=30000`
- `sense_count=63126`
- `concept_count=56497`
- `ambiguous_form_count=0`

Audit artifact:

- `data/lexicon/audits/words-30000-20260314-main-real-boundary-hardened.audit.summary.json`

Current audit summary:

- `suspicious_count=497`
- `linked_variant=1520`
- `possessive_surface_form=1`

Fresh verification already run:

- `PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_canonical_forms.py tools/lexicon/tests/test_audit_30k_semantics.py -q`
- `PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
- `wc -l data/lexicon/snapshots/words-30000-20260314-main-real-boundary-hardened/{lexemes,senses,concepts,ambiguous_forms}.jsonl`

Observed results:

- targeted: `69 passed`
- full suite: `221 passed`
- row counts: `30000 / 63126 / 56497 / 0`

## What Is Already Hardened

Tracked data-driven hardening is now in place for:

- irregular noun/plural forms
- compound irregular plurals such as `grandchildren -> grandchild`, `schoolchildren -> schoolchild`, and multiple `-men` plurals
- irregular verb past forms such as `became -> become`, `began -> begin`, `chose -> choose`, `got -> get`, `heard -> hear`, `held -> hold`, `kept -> keep`, `led -> lead`, `met -> meet`, `sold -> sell`, `told -> tell`, `understood -> understand`, `won -> win`, and `wore -> wear`
- linked lexicalized irregular forms such as `left`, `fed`, `felt`, `lost`, `thought`, `broken`, `driven`, `taken`, and `worn`
- bounded input-noise drops such as `childrens`, `womens`, `dont`, `atleast`, `bl`, `seperate`, `longterm`, and `lyin`

Relevant tracked files:

- `tools/lexicon/data/irregular_form_overrides.json`
- `tools/lexicon/data/irregular_verb_forms.json`
- `tools/lexicon/data/surface_form_overrides.json`
- `tools/lexicon/data/canonical_anomalies.json`

## Current Residual Risks

The remaining issues are no longer primarily morphology bugs. They are mostly common-word policy and entity classification issues.

High-value remaining items:

1. Entity category dataset for later LLM prompting
2. Bounded tail-exclusion policy for clear non-30K admissions
3. Optional linked-variant cleanup for `broke`

## Entity Categorization Goal

We discussed adding a tracked dataset for words that should not be treated as ordinary `general` vocabulary in later LLM prompting.

Recommended category families:

- `general`
- `name`
- `place`
- `brand`
- `entity_other`

The category data should live in tracked JSON/JSONL, not in code.

Examples that likely belong in non-general categories:

- names/surnames: `jemima`, `marla`, `mattis`, `mcarthur`, `mcclain`, `mccord`
- places: `maastricht`, `mainz`, `kinshasa`, `launceston`, `loire`
- brand/entity-like: `levi's`, `pinterest`

The goal is not necessarily to drop all of these from the 30K immediately. The goal is to make later LLM prompting category-aware.

## Bounded Tail-Exclusion Goal

We also discussed a bounded policy pass to remove obvious non-30K admissions without expanding canonicalization heuristics.

This means explicit dataset decisions for concrete bad tail items, for example:

- low-rank WordNet-backed backformation noise like `housekeep`, `overarch`, `antiquate`, `dilapidate`, `weightlift`, `tetri`, `preexist`
- bare letters and alphabet-like tokens if still admitted in later rebuilds
- short abbreviation/acronym noise if deemed out-of-scope for learner 30K
- nonstandard spellings and misspellings if they are not intentionally retained

This should be a finite, reviewable data pass, not more suffix logic.

## Current Near-Boundary Tail To Review

Current last admitted lexemes in the exact snapshot:

- `loveable`
- `lovey`
- `lowndes`
- `maastricht`
- `machinist`
- `mainz`
- `mandible`
- `manhole`
- `margate`
- `marginalised`
- `marigold`
- `marinade`
- `marla`
- `matted`
- `mattis`
- `mcarthur`
- `mcclain`
- `mccord`
- `melancholic`
- `merlot`

Current known low-rank interior admissions still present:

- `housekeep`
- `overarch`
- `antiquate`
- `dilapidate`
- `weightlift`
- `tetri`
- `preexist`

Current unresolved morphology-adjacent item:

- `broke` still behaves as plain `keep_separate` rather than linked lexicalized variant

## Recommended Next Session Order

1. Inspect the new entity-category and tail-drop candidate lists
2. Add tracked category dataset
3. Add bounded tail-drop dataset
4. Rebuild exact 30K boundary again
5. Re-run audit and verification
6. Refresh docs/status to the new exact boundary
7. Decide whether `broke` should be linked in this same PR or left for follow-up

## Important Constraints

- Keep word/mapping/category data in tracked data files, not hardcoded into logic
- Prefer bounded datasets over ever-broader deterministic rules
- Do not collapse forms just because they are semantically related
- Keep separately meaningful forms as separate lexemes, linked where appropriate
- Proper nouns / brands / surnames / places are anomaly candidates by default unless there is a strong reason not to classify them separately

## Repo Docs Already Updated

These docs reflect the current verified boundary-hardened state:

- `docs/plans/2026-03-14-lexicon-30k-exhaustive-semantic-audit-notes.md`
- `docs/plans/2026-03-14-real-30k-curation-and-variant-enrichment-report.md`
- `docs/status/project-status.md`

## Fresh-Context Restart Prompt

Use this in the next session:

`Continue the lexicon 30K hardening work from docs/plans/2026-03-14-lexicon-30k-next-pass-handoff.md. Stay on branch curate_real_30k_20260314 in worktree .worktrees/curate_real_30k_20260314. First finish the two agreed passes: tracked entity-category datasets for non-general words, and bounded tail-drop datasets for obvious non-30K admissions. Then rebuild the exact 30K boundary, rerun lexicon tests and audit, and refresh docs/status to the verified result.`
