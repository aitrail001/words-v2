# Dev Test Users Implementation — 2026-03-10

## Goal
Add two stable local-development test users for fast manual login/testing:
- `admin@admin.com` / `12345678`
- `user@user.com` / `12345678`

## Design
- keep this behavior development-only
- require an explicit config flag (`DEV_TEST_USERS_ENABLED`)
- enable that flag in local `docker-compose.yml` for the backend service
- seed lazily on the first real backend request instead of app startup so a fresh pre-migration DB does not break backend boot
- make seeding idempotent and guarantee role / active status / requested password

## Implementation
- added `backend/app/services/dev_test_users.py`
- added `dev_test_users_enabled` to `backend/app/core/config.py`
- updated `backend/app/main.py` to seed once per process in development when enabled, with graceful skip while DB schema is not ready
- enabled `DEV_TEST_USERS_ENABLED=true` for the backend service in `docker-compose.yml`
- added focused backend tests for config, seed helper behavior, and middleware gating

## Verification
- `PYTHONPATH=backend ../../.venv-backend/bin/python -m pytest backend/tests/test_config.py backend/tests/test_dev_test_users.py backend/tests/test_auth.py -q`
- live local verification via Docker stack + `POST /api/auth/login` and `GET /api/auth/me` for both seeded accounts
