---
name: lexicon-test-harness
description: Use when adding or maintaining offline lexicon tests, fixtures, or command-line verification for tools/lexicon.
---

# Lexicon Test Harness

Use this skill when adding tests for the lexicon admin pipeline.

## Rules

- Keep tests offline and deterministic.
- Prefer fixture-based JSONL tests over live API calls.
- Add failing tests before implementation when behavior changes.
- Verify batch and review flows with narrow, focused cases.

## Checks

- Run the smallest relevant test subset first.
- Confirm new fixtures load from disk exactly as expected.
- Confirm CLI help and operator docs mention any new commands.
