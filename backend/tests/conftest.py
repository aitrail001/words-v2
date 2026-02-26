from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app


@pytest.fixture
def mock_db():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock())
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


@pytest.fixture
async def client(mock_db, mock_redis):
    async def override_get_db():
        yield mock_db

    def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
