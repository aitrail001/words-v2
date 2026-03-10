# Lexicon Hardening Follow-up — 2026-03-10

## Scope
- preserve dirty local `main` safely before syncing to merged `origin/main`
- harden `compile-export` decision filtering against string boolean footguns
- reject `compile-export --decisions` runs that omit `--decision-filter`
- preserve legacy staged-review candidate metadata compatibility for admin review and publish-preview paths

## Changes
- backed up dirty root-checkout edits on `backup/main-dirty-20260310`
- wrote `/tmp/words-v2-dirty-main-backup.patch` as an extra local backup artifact
- fast-forwarded local `main` to merged `origin/main`
- added boolean-like coercion for `auto_accepted` and `review_required` in `tools/lexicon/compile_export.py`
- added explicit `--decisions requires --decision-filter` validation in `tools/lexicon/compile_export.py` and CLI error handling in `tools/lexicon/cli.py`
- added legacy metadata fallback for `label` / `gloss` in `backend/app/api/lexicon_reviews.py`
- added regression tests for compile filtering, CLI guardrails, and backend legacy staged-review metadata

## Verification
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests/test_compile_export.py tools/lexicon/tests/test_cli.py -q`
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_lexicon_reviews_api.py -q`
- `../../.venv-lexicon/bin/python -m pytest tools/lexicon/tests -q`
