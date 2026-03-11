# Lexicon Learner-First Entry Sourcing Implementation Plan

**Date:** 2026-03-11

## Goal

Implement the simplified learner-first lexicon pipeline that:
- sources common English words and high-value multiword entries,
- uses LLMs to choose learner-friendly meanings from source-grounded context,
- minimizes human review,
- imports only learner-ready entries into the local DB.

## Phase 1 — Freeze the learner-first contract
- finalize entry types: `word`, `phrasal_verb`, `fixed_expression`, `idiom`, `formulaic_expression`
- finalize per-category quotas
- finalize adaptive meaning caps by entry type/frequency band
- define schema evolution from `1.1.0` to the next learner-first version
- document hidden provenance fields vs user-facing fields

## Phase 2 — Build the entry acquisition layer
- add a word inventory builder from `wordfreq` for top common English words
- add a multiword candidate ingestion layer for WordNet/OEWN multiword lemmas
- add Kaikki/Wiktextract candidate-entry ingestion for multiword expressions
- add corpus-candidate ingestion hooks for formulaic/fixed-expression mining
- normalize, dedupe, and merge candidates across sources into one inventory store

## Phase 3 — Entry classification and ranking
- add deterministic entry-type classification rules
- add bounded LLM classification fallback for ambiguous multiword candidates
- add ranking formulas per category using frequency plus corpus/association hints
- apply category quotas after classification and ranking
- persist source provenance for each retained entry

## Phase 4 — Meaning-context assembly
- for words, assemble WordNet-grounded candidate sense context
- for multiword entries, assemble best available lexical and corpus context
- create a bounded prompt-ready context package per entry
- ensure the context package never requires manual sense picking first

## Phase 5 — LLM meaning selection and enrichment
- implement per-entry LLM prompts that ask for learner-friendly meaning choice
- request learner-facing definitions, examples, collocations, morphology, and notes in one pass
- extend output to include sense-level synonyms and other agreed schema fields
- keep WordNet/other-source IDs only as hidden provenance/context

## Phase 6 — Validation and gating
- strengthen output validation for forms, examples, enums, lists, and required fields
- add automated confidence/risk signals for unstable or malformed entries
- auto-accept clean outputs by default
- send only the residual exceptional tail to staged review

## Phase 7 — Import and staging split
- ensure the main DB receives only validated learner-ready entries
- keep unresolved entries in staging rather than publishing bare lexical rows
- preserve review metadata and source provenance for debugging/admin inspection
- verify the admin UI can inspect both staged and imported learner entries clearly

## Phase 8 — Rollout strategy
- start with a bounded pilot set for each category
- then scale to the full word quota before broad multiword expansion
- measure failure rates by category and prompt type
- tune only the categories that actually need extra gating

## Verification targets
- unit tests for entry normalization, dedupe, classification, ranking, and schema validation
- targeted tests for per-entry prompt building and output parsing
- import tests proving learner-ready entries land cleanly in DB
- admin inspection tests proving staged vs imported data remains understandable
