from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app
from app import main as app_main
from app.api.request_db_metrics import instrument_session_for_request, restore_session_after_request


@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    session.info = {}
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    return r


@pytest.fixture(autouse=True)
def disable_dev_test_user_bootstrap(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(app_main.settings, "environment", "test")
    monkeypatch.setattr(app_main.settings, "dev_test_users_enabled", False)
    monkeypatch.setattr(app_main, "ensure_dev_test_users", AsyncMock())
    app.state.dev_test_users_seeded = False


@pytest.fixture
async def client(mock_db, mock_redis):
    async def override_get_db(request: Request):
        instrument_session_for_request(request, mock_db)
        try:
            yield mock_db
        finally:
            restore_session_after_request(mock_db)

    def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
