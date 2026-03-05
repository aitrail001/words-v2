import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User
from app.models.word import Word
from app.models.meaning import Meaning


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
def auth_token():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    return token, user_id


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


def make_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )


def make_word(word: str = "bank", language: str = "en") -> Word:
    w = Word(id=uuid.uuid4(), word=word, language=language)
    return w


def make_meaning(word_id: uuid.UUID, definition: str = "A financial institution") -> Meaning:
    return Meaning(
        id=uuid.uuid4(),
        word_id=word_id,
        definition=definition,
        part_of_speech="noun",
        order_index=0,
    )


class TestWordSearch:
    @pytest.mark.asyncio
    async def test_search_requires_auth(self, client):
        response = await client.get("/api/words/search?q=bank")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_search_returns_results(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = make_word("bank")

        # First call: get_current_user lookup
        # Second call: search query
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        search_result = MagicMock()
        search_result.scalars.return_value.all.return_value = [word]
        mock_db.execute.side_effect = [user_result, search_result]

        response = await client.get(
            "/api/words/search?q=bank",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["word"] == "bank"

    @pytest.mark.asyncio
    async def test_search_empty_query(self, client, auth_token, mock_db):
        token, user_id = auth_token
        user = make_user(user_id)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = user_result

        response = await client.get(
            "/api/words/search?q=",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422


class TestWordDetail:
    @pytest.mark.asyncio
    async def test_get_word_by_id(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = make_word("bank")
        meaning = make_meaning(word.id, "A financial institution")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]
        mock_db.execute.side_effect = [user_result, word_result, meanings_result]

        response = await client.get(
            f"/api/words/{word.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["word"] == "bank"
        assert len(data["meanings"]) == 1
        assert data["meanings"][0]["definition"] == "A financial institution"

    @pytest.mark.asyncio
    async def test_get_word_not_found(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, word_result]

        fake_id = uuid.uuid4()
        response = await client.get(
            f"/api/words/{fake_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestWordLookup:
    @pytest.mark.asyncio
    async def test_lookup_existing_word(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = make_word("hello")
        meaning = make_meaning(word.id, "A greeting")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]
        mock_db.execute.side_effect = [user_result, word_result, meanings_result]

        response = await client.post(
            "/api/words/lookup",
            json={"word": "hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["word"] == "hello"
        assert len(data["meanings"]) == 1

    @pytest.mark.asyncio
    async def test_lookup_requires_auth(self, client):
        response = await client.post(
            "/api/words/lookup",
            json={"word": "hello"},
        )
        assert response.status_code == 401
