import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
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


@pytest.fixture
def auth_token():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    return token, user_id


def make_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )


def scalar_one_or_none_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestUserPreferencesApi:
    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_missing(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(None),
        ]

        response = await client.get(
            "/api/user-preferences",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accent_preference"] == "us"
        assert data["translation_locale"] == "zh-Hans"
        assert data["knowledge_view_preference"] == "cards"

    @pytest.mark.asyncio
    async def test_put_upserts_preferences(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(None),
        ]

        response = await client.put(
            "/api/user-preferences",
            json={
                "accent_preference": "au",
                "translation_locale": "es",
                "knowledge_view_preference": "list",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accent_preference"] == "au"
        assert data["translation_locale"] == "es"
        assert data["knowledge_view_preference"] == "list"
