# Lexicon Sense Ranking Design

**Date:** 2026-03-07

## Goal

Improve WordNet sense selection for learner-facing lexicon snapshots so broad, high-polysemy words like `run` and `set` do not collapse into noun-only outputs, while still preserving important noun meanings.

## Problem

The current selection path is effectively:
1. load WordNet synsets
2. normalize them into canonical sense dicts
3. sort by synset id string
4. take the first `max_senses`

This is deterministic, but it is not learner-oriented. For words like `run` and `set`, this can crowd out essential verb senses and over-represent specialized or lower-transfer noun senses.

## Design Summary

### 1. Learner-oriented sense ranking

Add a deterministic scoring function over canonical senses.

Each candidate sense receives a weighted score using:
- part-of-speech priority
- general-English gloss heuristics
- technical/specialized gloss penalties
- abstract/low-teachability penalties
- weak original-order tie-breaker

### 2. POS guardrails

When selecting a bounded set of senses:
- prefer high-value senses regardless of POS
- keep POS as a soft prior, not a hard quota
- cap specialized/domain-heavy senses within the first four selections
- penalize weak derived/action nouns when a stronger verb sense exists

This keeps genuinely useful noun meanings while preventing noun-only selections or weak nominalizations from crowding out core verb senses.

### 3. Adaptive sense cap

Replace the rigid global top-4 behavior with adaptive `4/6/8` selection:
- default: `4`
- promote to `6` for genuinely broad lemmas with strong cross-POS coverage
- promote to `8` only for very broad lemmas with enough high-quality remaining senses after the top six

The CLI `--max-senses` remains an operator override; the adaptive cap only applies within that ceiling.

## V1 Scoring Signals

### POS weights
- verb: strongest default learner priority
- noun: strong, but below verb for broad action words
- adjective: moderate
- adverb: lower

### Gloss heuristics
Boost senses whose glosses look like:
- everyday actions
- common physical actions
- common placement/operation meanings
- common collection/group meanings

Penalize senses whose glosses look like:
- mathematics
- baseball/cricket/sport-specific scoring
- theatre/film staging
- highly technical/scientific usage
- abstract low-transfer definitions

## Expected Behavior

For `run` and `set`, the selected set should surface core verb senses first, while letting only genuinely high-value noun senses earn their way into the top-ranked set.

For `max_senses=4`, the likely shape becomes:
- one or more high-value verbs
- a noun only if its learner-value score is competitive
- remaining slots chosen by score
- at most one specialized/domain-heavy sense unless unavoidable

## Non-Goals

This v1 does not attempt:
- curriculum-specific CEFR tuning in base selection
- corpus-driven contextual ranking
- lemma-specific hardcoded ranking tables
- UI-level display logic

## Verification Plan

Add tests covering:
- verb-first behavior on polysemous lemmas
- noun retention guardrail
- adaptive `4/6/8` cap expansion
- specialized-sense suppression in small bounded outputs
