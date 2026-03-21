---
name: lexicon-schema-guardrails
description: Use when editing lexicon enrichment schemas, normalization rules, or compiled export contracts.
---

# Lexicon Schema Guardrails

Use this skill when adding or changing structured lexicon payloads.

## Rules

- Prefer small, explicit schemas over inferred payloads.
- Keep validation pure and deterministic.
- Separate word, phrase, reference, and QC contracts.
- Keep lightweight reference entries intentionally minimal.

## Checks

- Validate field presence and bounded list lengths.
- Confirm compiled export still matches downstream import expectations.
- Confirm schema changes are reflected in offline fixtures and tests.
