import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User
from app.models.user_preference import UserPreference


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
    async def test_get_returns_defaults_when_missing_including_timezone(
        self, client, mock_db, auth_token
    ):
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
        assert data["show_translations_by_default"] is True
        assert data["review_depth_preset"] == "balanced"
        assert data["enable_confidence_check"] is True
        assert data["enable_word_spelling"] is True
        assert data["enable_audio_spelling"] is False
        assert data["show_pictures_in_questions"] is False
        assert data["timezone"] == "UTC"

    @pytest.mark.asyncio
    async def test_put_upserts_preferences_including_timezone(self, client, mock_db, auth_token):
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
                "show_translations_by_default": False,
                "review_depth_preset": "deep",
                "enable_confidence_check": False,
                "enable_word_spelling": False,
                "enable_audio_spelling": True,
                "show_pictures_in_questions": True,
                "timezone": "Australia/Melbourne",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accent_preference"] == "au"
        assert data["translation_locale"] == "es"
        assert data["knowledge_view_preference"] == "list"
        assert data["show_translations_by_default"] is False
        assert data["review_depth_preset"] == "deep"
        assert data["enable_confidence_check"] is False
        assert data["enable_word_spelling"] is False
        assert data["enable_audio_spelling"] is True
        assert data["show_pictures_in_questions"] is True
        assert data["timezone"] == "Australia/Melbourne"

    @pytest.mark.asyncio
    async def test_put_updates_existing_preferences_including_timezone(
        self, client, mock_db, auth_token
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        existing = UserPreference(
            user_id=user_id,
            accent_preference="us",
            translation_locale="zh-Hans",
            knowledge_view_preference="cards",
            show_translations_by_default=True,
            review_depth_preset="balanced",
            enable_confidence_check=True,
            enable_word_spelling=True,
            enable_audio_spelling=False,
            show_pictures_in_questions=False,
            timezone="UTC",
        )

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(existing),
        ]

        response = await client.put(
            "/api/user-preferences",
            json={
                "accent_preference": "uk",
                "translation_locale": "ja",
                "knowledge_view_preference": "tags",
                "show_translations_by_default": False,
                "review_depth_preset": "gentle",
                "enable_confidence_check": False,
                "enable_word_spelling": False,
                "enable_audio_spelling": True,
                "show_pictures_in_questions": True,
                "timezone": "Europe/Berlin",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accent_preference"] == "uk"
        assert data["translation_locale"] == "ja"
        assert data["knowledge_view_preference"] == "tags"
        assert data["show_translations_by_default"] is False
        assert data["review_depth_preset"] == "gentle"
        assert data["enable_confidence_check"] is False
        assert data["enable_word_spelling"] is False
        assert data["enable_audio_spelling"] is True
        assert data["show_pictures_in_questions"] is True
        assert data["timezone"] == "Europe/Berlin"
        assert existing.accent_preference == "uk"
        assert existing.show_translations_by_default is False
        assert existing.timezone == "Europe/Berlin"
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_put_legacy_payload_without_timezone_preserves_existing_timezone(
        self, client, mock_db, auth_token
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        existing = UserPreference(
            user_id=user_id,
            accent_preference="us",
            translation_locale="zh-Hans",
            knowledge_view_preference="cards",
            show_translations_by_default=True,
            review_depth_preset="balanced",
            enable_confidence_check=True,
            enable_word_spelling=True,
            enable_audio_spelling=False,
            show_pictures_in_questions=False,
            timezone="Europe/Paris",
        )

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(existing),
        ]

        response = await client.put(
            "/api/user-preferences",
            json={
                "accent_preference": "uk",
                "translation_locale": "ja",
                "knowledge_view_preference": "tags",
                "show_translations_by_default": False,
                "review_depth_preset": "gentle",
                "enable_confidence_check": False,
                "enable_word_spelling": False,
                "enable_audio_spelling": True,
                "show_pictures_in_questions": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/Paris"
        assert existing.timezone == "Europe/Paris"

    @pytest.mark.asyncio
    async def test_put_rejects_unknown_timezone(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(None),
        ]

        response = await client.put(
            "/api/user-preferences",
            json={
                "accent_preference": "us",
                "translation_locale": "zh-Hans",
                "knowledge_view_preference": "cards",
                "show_translations_by_default": True,
                "review_depth_preset": "balanced",
                "enable_confidence_check": True,
                "enable_word_spelling": True,
                "enable_audio_spelling": False,
                "show_pictures_in_questions": False,
                "timezone": "Mars/Base",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422
