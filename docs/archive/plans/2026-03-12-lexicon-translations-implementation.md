# 2026-03-12 — Lexicon learner-translation PR 2 implementation

## Scope

Implement PR 2 of the lexicon tool roadmap: learner-facing translations for `zh-Hans`, `es`, `ar`, `pt-BR`, and `ja`.

## Agreed constraints

1. Translation generation belongs in the lexicon enrichment step.
2. Required translated fields per sense are:
   - `definition`
   - `usage_note`
   - `examples` (artifact/compiled level)
3. Current DB import will only write meaning-level translated definitions into `translations`.
4. Example translations and translated usage notes remain in JSONL artifacts and compiled outputs for now.
5. Avoid large backend/API schema expansion in this PR.

## Design

### Enrichment payload

Extend per-sense learner enrichment payloads with:

- `translations`: object keyed by locale
- each locale entry contains:
  - `definition`
  - `usage_note`
  - `examples` (list of translated strings aligned to the English `examples` list)

Required locales:
- `zh-Hans`
- `es`
- `ar`
- `pt-BR`
- `ja`

### Validation

1. Reject missing required locale keys.
2. Reject missing translated `definition`.
3. Reject missing translated `usage_note`.
4. Reject missing or empty translated `examples` list.
5. Reject translated `examples` length mismatch with English examples length.

### Compile/export

Preserve `translations` at the compiled sense level.

### Import DB

For each imported meaning:
- upsert `Translation` rows for the translated `definition` per required locale
- keep example/usage-note translations in artifacts only for now

### Verification

1. Lexicon enrichment tests for translation validation in per-sense and per-word modes.
2. Compile-export test that preserves translations in compiled rows.
3. Import test that writes meaning translations for the five locales.
4. Targeted backend model/API verification only if current API already exposes translations or import changes require it.

## Expected follow-up

PR 3 remains the optional ambiguous-form LLM adjudication slice from `docs/plans/2026-03-12-lexicon-canonical-registry-translations-multi-pr-plan.md`.
