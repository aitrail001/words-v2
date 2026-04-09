# Import Cache Canonical Hardening

## Goal

Preserve `import_sources` as the canonical shared cache record for each EPUB hash/version, prevent deleted cache reactivation from clearing the tombstone before regeneration completes, and make historical import jobs consistently report cache unavailability when the shared cache cannot serve entries.

## Scope

- Keep deleted canonical cache rows tombstoned during re-import until regeneration succeeds.
- Clear `deleted_at` only after the cache has been rebuilt successfully.
- Treat non-completed or entry-less cache states as unavailable in user import review and list-creation flows.
- Add regression tests for the canonical-source lifecycle and the user-facing API behavior.

## Verification

- `backend/tests/test_source_imports_service.py`
- `backend/tests/test_import_jobs_api.py`
- `backend/tests/test_epub_processing.py`
