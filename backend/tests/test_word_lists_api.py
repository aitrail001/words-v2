import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
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


def make_user(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        password_hash=hash_password("password123"),
    )


class TestWordListsApi:
    @pytest.mark.asyncio
    async def test_list_word_lists(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        list_item = WordList(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Imported from book",
            source_type="epub",
            created_at=datetime.now(timezone.utc),
        )
        lists_result = MagicMock()
        lists_result.scalars.return_value.all.return_value = [list_item]

        mock_db.execute.side_effect = [user_result, lists_result]

        response = await client.get(
            "/api/word-lists",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["name"] == "Imported from book"

    @pytest.mark.asyncio
    async def test_get_word_list_not_found(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [user_result, list_result]

        response = await client.get(
            f"/api/word-lists/{list_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Word list not found"

    @pytest.mark.asyncio
    async def test_add_word_list_item(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        word_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        list_model = WordList(
            id=list_id,
            user_id=user_id,
            name="Imported from book",
            created_at=datetime.now(timezone.utc),
        )
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = list_model

        existing_item_result = MagicMock()
        existing_item_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [user_result, list_result, existing_item_result]

        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.added_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            f"/api/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"word_id": str(word_id), "frequency_count": 2},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["word_id"] == str(word_id)
        assert body["frequency_count"] == 2

    @pytest.mark.asyncio
    async def test_delete_word_list_item_not_found(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        item_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        list_model = WordList(
            id=list_id,
            user_id=user_id,
            name="Imported from book",
            created_at=datetime.now(timezone.utc),
        )
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = list_model

        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [user_result, list_result, item_result]

        response = await client.delete(
            f"/api/word-lists/{list_id}/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Word list item not found"
