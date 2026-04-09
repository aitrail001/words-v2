# Real 30K Curation And Variant Enrichment Report

Date: 2026-03-14
Owner: Codex
Scope: Deterministic lexicon snapshot preparation for the later LLM stage, with no LLM requests in this slice

## Summary

This slice did six things:

1. Added explicit variant metadata to interim `lexemes.jsonl` rows for headwords that remain separate because they have their own meanings but are still linked to a base form.
2. Added and expanded a tracked canonical anomaly override list for bounded non-generalizable edge cases so the pipeline stops tail-chasing on rare names, brands, lexicalized plurals, and explicit regular-plural exceptions.
3. Moved rule-word lists out of code and into tracked lexicon data files so future list maintenance stays data-only where possible.
4. Added a possessive hardening pass that collapses true possessive surface forms to their base lexeme while leaving genuine contractions alone.
5. Added tracked entity-category and bounded tail-exclusion datasets so the common-word rollout can keep non-general entries explicit and drop concrete bad admissions without widening heuristics.
6. Produced a new dated deterministic snapshot containing a real post-collapse 30,000-word common-word inventory ready for the later LLM enrichment stage.

The later enrichment path can now detect linked lexicalized variants such as `left`, `best`, `better`, `meeting`, and similar forms, and use a stricter prompt that tells the model not to duplicate the base-word meanings.

## Interim Schema / Prompt Change

Interim lexeme rows now include:

- `is_variant_with_distinct_meanings`
- `variant_base_form`
- `variant_relationship`
- `entity_category`

These fields are populated directly from deterministic canonicalization/build-base output when a word:

- remains its own headword
- is linked to a base form
- should still be treated as a separate learner entry because it has distinct meanings

The per-word enrichment prompt now adds variant-specific instructions only for those flagged lexemes:

- do not repeat ordinary meanings already covered by the base word
- generate only meanings that are distinct/special to the surface form
- include a short usage note that states it is another form of the base word

And for non-general entity rows it now adds category-aware guidance so the later LLM stage stays grounded in the named-entity or specialized-entity reading instead of drifting toward similarly spelled common words.

## Data-Driven Rule / Anomaly Layer

Tracked files:

- `tools/lexicon/data/canonical_anomalies.json`
- `tools/lexicon/data/canonical_rule_sets.json`
- `tools/lexicon/data/irregular_form_overrides.json`
- `tools/lexicon/data/irregular_verb_forms.json`
- `tools/lexicon/data/entity_categories.json`
- `tools/lexicon/data/surface_form_overrides.json`
- `tools/lexicon/data/tail_exclusions.json`

Supported override actions in this slice:

- `force_keep_separate`
- `force_collapse_to_canonical`
- irregular non-verb `collapse_to_canonical`
- irregular verb `collapse_to_canonical`
- irregular lexicalized `keep_both_linked`

Purpose:

- catch bounded non-generalizable tail cases that are not worth solving with ever-broader suffix rules
- keep the deterministic core strict while making the exception layer explicit and auditable
- keep word lists and mappings in tracked data rather than hardcoded in logic

Examples now forced `keep_separate`:

- `angeles`
- `levi's`
- `o'brien`
- `o'connor`
- `sanders`
- `analytics`
- `midfielder`
- `glasses`
- `curated`
- `nuanced`
- `reputed`

Examples now forced `collapse_to_canonical`:

- `rupees -> rupee`
- `pesos -> peso`
- `millennials -> millennial`
- `boomers -> boomer`
- `orioles -> oriole`
- `perks -> perk`

Examples now normalized or filtered before selection:

- `gov't -> government`
- `int'l -> international`
- `ya'll -> y'all`
- drop `n't`
- drop one-letter apostrophe forms like `a's`

## Verification

Commands run in `/Users/johnson/AI/src/words-v2/.worktrees/curate_real_30k_20260314`:

```bash
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_build_base.py tools/lexicon/tests/test_models.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_enrich.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_canonical_forms.py tools/lexicon/tests/test_audit_30k_semantics.py -q
/Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q
PYTHONPATH=. /Users/johnson/AI/src/words-v2/.venv-lexicon/bin/python tools/lexicon/audit_30k_semantics.py
```

Observed results:

- targeted coverage for build-base / CLI / canonical / audit / enrich paths: `160 passed in 4.07s`
- full lexicon suite: `227 passed in 5.50s`
- snapshot validation on the final exact artifact: `0` errors
- rebuilt exact 30K snapshot: `30000` lexemes, `63126` senses, `56507` concepts, `0` ambiguous rows
- rebuilt audit summary: `30000` lexemes, `553` review-priority rows, `1521` linked variants, explicit entity counts `name=36`, `place=11`, `brand=5`, `entity_other=4`

## Real 30K Search Outcome

Goal: get exactly 30,000 surviving lexemes after deterministic canonical collapse, not just request 30,000 raw `wordfreq` tokens.

Initial pre-hardening search earlier in the slice showed a lower request window was sufficient, but later possessive hardening, compound-irregular collapse, expanded irregular verb coverage, explicit tail exclusions, and entity-category tagging removed or reclassified more survivors and shifted the exact boundary upward again. The final exact post-hardening search converged to:

- `39484 -> 29999`
- `39485 -> 30000`
- `39487 -> 30001`

Final chosen request window:

- `requested_top_words=39485`

## Final Snapshot

Output directory:

- `data/lexicon/snapshots/words-30000-20260314-main-real-entity-tail-hardened`

Final exact counts:

- `lexeme_count=30000`
- `sense_count=63126`
- `concept_count=56507`
- `ambiguous_form_count=0`

Snapshot id:

- `lexicon-20260314-wordnet-wordfreq`

This snapshot is deterministic-only and ready for the later LLM enrichment stage.

## Variant Metadata Evidence

Example flagged rows in `lexemes.jsonl` now include:

- `being -> be`
- `going -> go`
- `best -> good`
- `better -> good`
- `left -> leave`

These rows carry:

- `is_variant_with_distinct_meanings=true`
- `variant_base_form=<base>`
- `variant_relationship='lexicalized_form'`

## Post-Hardening Quality Audit

Representative previously risky cases now behave as intended:

- `glasses`: `keep_separate`
- `angeles`: `keep_separate`
- `levi's`: `keep_separate`
- `o'brien`: `keep_separate`
- `o'connor`: `keep_separate`
- `sanders`: `keep_separate`
- `analytics`: `keep_separate`
- `midfielder`: `keep_separate`
- `curated`: `keep_separate`
- `nuanced`: `keep_separate`
- `reputed`: `keep_separate`
- `rupees`: `collapse_to_canonical -> rupee`
- `pesos`: `collapse_to_canonical -> peso`
- `millennials`: `collapse_to_canonical -> millennial`
- `boomers`: `collapse_to_canonical -> boomer`
- `orioles`: `collapse_to_canonical -> oriole`
- `perks`: `collapse_to_canonical -> perk`
- `children`: `collapse_to_canonical -> child`
- `grandchildren`: `collapse_to_canonical -> grandchild`
- `women`: `collapse_to_canonical -> woman`
- `teeth`: `collapse_to_canonical -> tooth`
- `feet`: `collapse_to_canonical -> foot`
- `mice`: `collapse_to_canonical -> mouse`
- `geese`: `collapse_to_canonical -> goose`
- `diagnoses`: `collapse_to_canonical -> diagnosis`
- `ate`: `collapse_to_canonical -> eat`
- `became`: `collapse_to_canonical -> become`
- `began`: `collapse_to_canonical -> begin`
- `been`: `collapse_to_canonical -> be`
- `brought`: `collapse_to_canonical -> bring`
- `caught`: `collapse_to_canonical -> catch`
- `did`: `collapse_to_canonical -> do`
- `got`: `collapse_to_canonical -> get`
- `came`: `collapse_to_canonical -> come`
- `bought`: `collapse_to_canonical -> buy`
- `gave`: `collapse_to_canonical -> give`
- `heard`: `collapse_to_canonical -> hear`
- `held`: `collapse_to_canonical -> hold`
- `had`: `collapse_to_canonical -> have`
- `kept`: `collapse_to_canonical -> keep`
- `led`: `collapse_to_canonical -> lead`
- `lent`: `collapse_to_canonical -> lend`
- `made`: `collapse_to_canonical -> make`
- `meant`: `collapse_to_canonical -> mean`
- `met`: `collapse_to_canonical -> meet`
- `seen`: `collapse_to_canonical -> see`
- `slept`: `collapse_to_canonical -> sleep`
- `sold`: `collapse_to_canonical -> sell`
- `sought`: `collapse_to_canonical -> seek`
- `spoke`: `collapse_to_canonical -> speak`
- `stood`: `collapse_to_canonical -> stand`
- `taught`: `collapse_to_canonical -> teach`
- `took`: `collapse_to_canonical -> take`
- `told`: `collapse_to_canonical -> tell`
- `understood`: `collapse_to_canonical -> understand`
- `was`: `collapse_to_canonical -> be`
- `went`: `collapse_to_canonical -> go`
- `were`: `collapse_to_canonical -> be`
- `woke`: `collapse_to_canonical -> wake`
- `won`: `collapse_to_canonical -> win`
- `wore`: `collapse_to_canonical -> wear`
- `left`: `keep_both_linked -> leave`
- `fed`: `keep_both_linked -> feed`
- `felt`: `keep_both_linked -> feel`
- `given`: `keep_both_linked -> give`
- `gone`: `keep_both_linked -> go`
- `lost`: `keep_both_linked -> lose`
- `paid`: `keep_both_linked -> pay`
- `thought`: `keep_both_linked -> think`
- `broken`: `keep_both_linked -> break`
- `driven`: `keep_both_linked -> drive`
- `drunk`: `keep_both_linked -> drink`
- `fallen`: `keep_both_linked -> fall`
- `forgotten`: `keep_both_linked -> forget`
- `hidden`: `keep_both_linked -> hide`
- `spent`: `keep_both_linked -> spend`
- `taken`: `keep_both_linked -> take`
- `worn`: `keep_both_linked -> wear`
- `clothes`: `keep_separate`
- `goods`: `keep_separate`
- `spirits`: `keep_separate`
- `arms`: `keep_separate`
- `quarters`: `keep_separate`
- `regards`: `keep_separate`

## Exhaustive Audit Outcome

Tracked audit artifacts:

- `data/lexicon/audits/words-30000-20260314-main-real-entity-tail-hardened.audit.json`
- `data/lexicon/audits/words-30000-20260314-main-real-entity-tail-hardened.audit.summary.json`

Semantic audit conclusions in this slice:

- the possessive surface-form class was a real deterministic gap and is now handled generically
- detached clitic fragments and abbreviation spellings are now handled through data-driven surface-form normalization/drop rules before selection
- apostrophized proper-name survivors are now tracked explicitly in anomaly data rather than relying on incidental keep-separate behavior
- the remaining derived bucket is mostly productive standalone nouns/adjectives plus a small proper-name tail now tracked explicitly in anomalies
- the remaining plural bucket is largely lexicalized plural/common-noun territory rather than ordinary plural duplication
- the main residual review bucket before PR/merge is now the small apostrophe/abbreviation tail

Irregular hardening follow-up:

- new tracked datasets now cover audited irregular noun/plural and irregular verb misses
- compound irregular suffixes such as `grandchildren -> grandchild` are now generated from the tracked irregular-base data instead of ad hoc code lists
- new anomaly rows now pin audited lexicalized plural false positives instead of broadening suffix logic
- exact request window shifted from the earlier `39331` checkpoint to the final `39485`
- rebuilt exact 30K snapshot remains deterministic-only with `0` ambiguous rows
- rebuilt audit summary for `words-30000-20260314-main-real-entity-tail-hardened`: `30000` lexemes, `553` review-priority rows, `1521` linked variants, and `56` explicit non-general entity rows
- the review-priority increase is expected because explicit `entity_category` tags are now counted deliberately rather than being hidden in the tail
- the bounded tail-exclusion pass removed concrete admissions such as `housekeep`, `overarch`, `antiquate`, `dilapidate`, `weightlift`, `tetri`, `preexist`, `json`, `mcl`, `mov`, `mvc`, `mut`, `nok`, `nrg`, `nwa`, and `opa`
- the residual boundary tail is now mostly categorized names/places plus a smaller lexical tail such as `newberry`, `nilsson`, `oberlin`, `oliveira`, `osgood`, `peckham`, and `petrov`, which are carried explicitly as non-general entity rows instead of being treated as ordinary learner vocabulary

## Deliverable

The final deliverable for the next stage is:

- a real deterministic 30K lexeme snapshot in `data/lexicon/snapshots/words-30000-20260314-main-real`
- a real deterministic 30K lexeme snapshot in `data/lexicon/snapshots/words-30000-20260314-main-real-entity-tail-hardened`
- with variant-aware interim metadata already embedded in `lexemes.jsonl`
- with explicit `entity_category` metadata for later prompt specialization
- with the bounded anomaly tail resolved deterministically into explicit tracked overrides
- with rule-word lists stored in tracked data files rather than hardcoded in logic
- ready for later LLM enrichment without duplicating base-word meanings for linked lexicalized variants
