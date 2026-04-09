# Lexicon 30K Exhaustive Semantic Audit Design

Date: 2026-03-14
Owner: Codex

## Goal

Run an exhaustive semantic audit over the full deterministic 30K lexeme set before PR, including near-boundary candidates whose selection can change after additional collapses, and move lexeme-specific canonicalization corrections into tracked datasets instead of endlessly broadening the generic deterministic rules.

## Audit Policy

1. Every lexeme in the 30K snapshot must be covered by the audit process.
2. Proper nouns, brands, surnames, and place names are anomaly candidates by default unless there is a strong reason to keep them via the general deterministic rules.
3. An anomaly-list entry does not mean "drop this word". It means "preserve the intended 30K outcome via an explicit tracked deterministic override".
4. The anomaly list should stay narrow and auditable. It should not become a replacement canonicalization engine.

## Chosen Approach

### 1. Full 30K audit inventory

Generate a machine-readable audit inventory covering all 30,000 lexemes with:

- base lexeme metadata
- canonical decision metadata
- source forms
- variant linkage
- heuristic risk buckets

This makes the audit exhaustive in coverage even though not every lexeme requires the same amount of human attention.

### 2. Risk-bucket manual review

Manually inspect every lexeme in the suspicious buckets, not just samples.

Suspicious buckets include:

- proper-name-like / surname-like / place-name-like
- brand/product-like
- lexicalized plural candidates
- irregular plural candidates
- irregular comparative / superlative candidates
- irregular verb-form candidates
- derived `-ed` / `-ing` / `-er` forms with possible independent meanings
- unusual low-frequency forms
- apostrophe/hyphen oddities
- words lacking strong WordNet grounding but still surviving the list

Safe buckets are still included in the audit inventory, but do not require literal one-by-one manual review unless a later pattern suggests they should be escalated.

### 3. Use tracked datasets for bounded lexical knowledge

If a word is clearly tricky and non-generalizable, record it in tracked data instead of complicating the generic rules further.

The data split should stay explicit:

- anomaly overrides for keep-separate / force-collapse exceptions
- irregular non-verb form mappings
- irregular verb-form mappings

Code should implement lookup and decision logic. Lexeme-specific knowledge should live in the datasets.

### 4. Rebuild after audit

After dataset updates, rebuild the dated 30K snapshot and confirm:

- exact 30,000 lexeme rows remain
- no new ambiguous tail appears
- reviewed risky words resolve as intended
- any freed slots are filled from the next valid near-boundary candidates

## Why This Approach

- It is exhaustive in coverage across the entire 30K set.
- It applies manual effort where semantic errors are actually plausible.
- It avoids wasting time pretending that obvious safe function words need the same level of semantic review as `angeles` or `pinterest`.
- It keeps the deterministic core bounded and auditable.
- It separates generic morphology from explicit lexical knowledge.
- It handles selection-quality changes that only appear once new collapses free boundary slots.

## Success Criteria

1. A tracked audit inventory exists for all 30,000 lexemes.
2. Every suspicious bucket word is manually classified.
3. New tracked dataset entries are added only where they are more appropriate than generic hardening.
4. The rebuilt 30K snapshot remains exact in size and stable in quality.
5. Boundary-band replacements introduced by new collapses are also audited before finalization.
