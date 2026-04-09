# EPUB Generic Word Lists Implementation Plan

**Goal:** Replace the preliminary EPUB import flows with one review-first generic import pipeline that reuses existing learner-catalog entries and creates normal mixed-entry word lists.

**Architecture:** Add a canonical cached import-source layer plus per-user import sessions, migrate `WordListItem` from `word_id` to generic `entry_type`/`entry_id` references, and route EPUB extraction/matching through dedicated services that only persist canonical matched entries and aggregate counts. Reuse learner-catalog and knowledge-map hydration for review and list display.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Celery, PostgreSQL, Next.js, Jest, pytest

## Planned slices

1. Add schema + migrations for `ImportSource`, `ImportSourceEntry`, and generic `WordListItem`.
2. Replace EPUB task logic with deterministic extraction/matching services and import-source caching.
3. Reshape `ImportJob` into a user review session linked to an `ImportSource`.
4. Replace word-list APIs with generic entry CRUD, review-entry listing, and create-from-selection flows.
5. Replace the frontend imports page with upload -> processing -> review -> create-list flow.
6. Add targeted backend/frontend tests for no raw-text persistence, no lexicon row creation, cache reuse, generic list behavior, and review filtering/selection.
7. Update `docs/status/project-status.md` with fresh verification evidence.
