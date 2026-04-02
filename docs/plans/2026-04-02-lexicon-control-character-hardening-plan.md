# Lexicon Control Character Hardening Plan

Goal: prevent NUL and other control-character corruption from entering `words.enriched.jsonl` or the compiled-review import path.

Scope:
- reject control characters during enrichment payload normalization
- fail fast before JSONL write/append when any row contains control characters
- sanitize compiled review imports before persistence as a defensive backstop

Verification:
- tools/lexicon normalization tests for control-character rejection
- tools/lexicon JSONL IO tests for fail-fast writes
- backend compiled-review API test proving import sanitization before persistence
