# Lexicon 30K Exhaustive Semantic Audit Notes

Date: 2026-03-14
Owner: Codex

## Scope

Manual semantic review focused on:

- current deterministic 30K snapshot outcomes
- near-boundary candidates that can enter the 30K after new collapses
- audited irregular noun/plural, irregular verb, and lexicalized irregular-form behavior

## Audited Irregular Misses Fixed Deterministically

These were confirmed as true inflectional duplicates and moved into tracked irregular-form datasets rather than left to generic suffix heuristics:

- `children -> child`
- `grandchildren -> grandchild`
- compound `-children` / `-men` / `-women` plurals now resolve through the tracked irregular-base datasets
- `men -> man`
- `women -> woman`
- `teeth -> tooth`
- `feet -> foot`
- `mice -> mouse`
- `geese -> goose`
- `diagnoses -> diagnosis`
- `ate -> eat`
- `been -> be`
- `brought -> bring`
- `caught -> catch`
- `did -> do`
- `came -> come`
- `bought -> buy`
- `became -> become`
- `began -> begin`
- `gave -> give`
- `got -> get`
- `had -> have`
- `heard -> hear`
- `held -> hold`
- `kept -> keep`
- `led -> lead`
- `lent -> lend`
- `made -> make`
- `meant -> mean`
- `met -> meet`
- `seen -> see`
- `slept -> sleep`
- `sold -> sell`
- `sought -> seek`
- `spoke -> speak`
- `stood -> stand`
- `taught -> teach`
- `took -> take`
- `told -> tell`
- `understood -> understand`
- `was -> be`
- `went -> go`
- `were -> be`
- `woke -> wake`
- `won -> win`
- `wore -> wear`

## Lexicalized Irregular Forms Kept Separate But Linked

These remain separate learner entries because they have their own meanings/usages beyond ordinary inflectional duplication:

- `left -> leave`
- `fed -> feed`
- `felt -> feel`
- `given -> give`
- `gone -> go`
- `lost -> lose`
- `paid -> pay`
- `thought -> think`
- `better -> good`
- `best -> good`
- `worse -> bad`
- `worst -> bad`
- `broken -> break`
- `driven -> drive`
- `drunk -> drink`
- `fallen -> fall`
- `forgotten -> forget`
- `hidden -> hide`
- `spent -> spend`
- `taken -> take`
- `worn -> wear`

## Lexicalized Plurals Forced To Stay Separate

These were previously at risk of false suffix collapse and are now pinned in anomaly data instead of trying to broaden the generic plural logic:

- `arms`
- `clothes`
- `goods`
- `quarters`
- `regards`
- `spirits`
- `levi's`

## Forms Intentionally Left Separate

These currently remain separate because the surface form has a distinct lexicalized noun/adjective sense or would require broader policy work beyond the bounded irregular-form slice:

- `saw`
- `thought`
- `data`
- `people`

## Boundary Result

After the new irregular collapses, explicit tail exclusions, and entity-category pass, the exact top-word request boundary shifted upward again:

- `39484 -> 29999`
- `39485 -> 30000`
- `39487 -> 30001`

Exact rebuilt snapshot:

- `data/lexicon/snapshots/words-30000-20260314-main-real-entity-tail-hardened`

## Remaining Follow-Up Candidates

These were surfaced during audit and now split cleanly between deterministic policy and later prompt behavior:

- irregular/adjectival forms that still remain plain `keep_separate` rather than linked variants, most notably `broke`
- the bounded tail-exclusion dataset now removes low-rank admissions such as `housekeep`, `overarch`, `antiquate`, `dilapidate`, `weightlift`, `tetri`, `preexist`, `json`, `mcl`, `mov`, `mvc`, `mut`, `nok`, `nrg`, `nwa`, and `opa`
- near-boundary anomaly candidates are now explicitly tracked through `entity_category` rows, including names/place-like entries such as `lowndes`, `maastricht`, `mainz`, `marla`, `mattis`, `mcarthur`, `mcclain`, `mccord`, `kinshasa`, `launceston`, `loire`, `newberry`, `nilsson`, `oberlin`, `oliveira`, `osgood`, `peckham`, and `petrov`
- common-word quality work is now mostly a bounded dataset question rather than a remaining morphology question

## Verification Evidence

- targeted lexicon coverage for build-base / CLI / canonical / audit / enrich paths: `160 passed in 4.07s`
- full lexicon test suite: `227 passed in 5.50s`
- rebuilt exact 30K snapshot at `39485` with `lexeme_count=30000`, `sense_count=63126`, `concept_count=56507`, and `ambiguous_form_count=0`
- rebuilt audit summary for `words-30000-20260314-main-real-entity-tail-hardened`: `suspicious_count=553`, `linked_variant=1521`, `entity_category_counts={name:36, place:11, brand:5, entity_other:4}`
- `validate_snapshot_files` on the final snapshot returned `0` errors
