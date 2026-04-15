#!/usr/bin/env bash
# Canonical CI-relevant suite manifest.
# Update this file first when CI-relevant tests or lane memberships change;
# Downstream runner scripts should source these definitions rather than duplicate them.

declare -p FAST_BACKEND_SUBSET >/dev/null 2>&1 || readonly -a FAST_BACKEND_SUBSET=(
  tests/test_imports_api.py
  tests/test_import_jobs_api.py
  tests/test_source_imports_service.py
  tests/test_lexicon_compiled_review_models.py
  tests/test_review_service.py
  tests/test_review_api.py
  tests/test_user_preferences_api.py
  tests/test_learner_knowledge_models.py
  tests/test_knowledge_map_api.py
)

declare -p FAST_FRONTEND_SUBSET_COMMAND >/dev/null 2>&1 || readonly -a FAST_FRONTEND_SUBSET_COMMAND=(npm run test:review)

declare -p E2E_SMOKE_SUITES >/dev/null 2>&1 || readonly -a E2E_SMOKE_SUITES=(smoke route-runtime-smoke)
declare -p E2E_REQUIRED_FULL_SUITES >/dev/null 2>&1 || readonly -a E2E_REQUIRED_FULL_SUITES=(review-srs admin user route-runtime-full)

declare -p FRONTEND_FAST_MODES >/dev/null 2>&1 || readonly -a FRONTEND_FAST_MODES=(lint subset)
declare -p FRONTEND_FULL_MODES >/dev/null 2>&1 || readonly -a FRONTEND_FULL_MODES=(lint subset test build)

declare -p ADMIN_FAST_MODES >/dev/null 2>&1 || readonly -a ADMIN_FAST_MODES=(lint test)
declare -p ADMIN_FULL_MODES >/dev/null 2>&1 || readonly -a ADMIN_FULL_MODES=(lint test build)

declare -p LEXICON_GATE_MODES >/dev/null 2>&1 || readonly -a LEXICON_GATE_MODES=(full smoke)
