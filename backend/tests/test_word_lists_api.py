import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.api import word_lists as word_lists_api
from app.models.user import User
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem
from app.models.meaning import Meaning
from app.models.translation import Translation


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
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

        response = await client.get("/api/word-lists", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json()[0]["name"] == "Imported from book"

    @pytest.mark.asyncio
    async def test_create_empty_word_list(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, duplicate_result]

        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            "/api/word-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Manual list"},
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Manual list"

    @pytest.mark.asyncio
    async def test_create_empty_word_list_rejects_duplicate_name(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = WordList(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Manual list",
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.side_effect = [user_result, duplicate_result]

        response = await client.post(
            "/api/word-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Manual list"},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Word list name already exists"

    @pytest.mark.asyncio
    async def test_add_word_list_item_uses_generic_entry_reference(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        entry_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = WordList(
            id=list_id,
            user_id=user_id,
            name="Generic list",
            created_at=datetime.now(timezone.utc),
        )
        catalog_row = MagicMock(
            display_text="make up for",
            normalized_form="make up for",
            browse_rank=123,
            cefr_level="B2",
            phrase_kind="phrasal_verb",
            primary_part_of_speech=None,
        )
        catalog_result = MagicMock()
        catalog_result.scalar_one_or_none.return_value = catalog_row
        existing_item_result = MagicMock()
        existing_item_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [user_result, list_result, catalog_result, existing_item_result]

        async def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.added_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        response = await client.post(
            f"/api/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"entry_type": "phrase", "entry_id": str(entry_id), "frequency_count": 2},
        )

        assert response.status_code == 201
        assert response.json()["entry_type"] == "phrase"
        assert response.json()["entry_id"] == str(entry_id)

    @pytest.mark.asyncio
    async def test_delete_word_list_item_not_found(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        item_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = WordList(
            id=list_id,
            user_id=user_id,
            name="Imported from book",
            created_at=datetime.now(timezone.utc),
        )
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, list_result, item_result]

        response = await client.delete(
            f"/api/word-lists/{list_id}/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Word list item not found"

    @pytest.mark.asyncio
    async def test_update_word_list_preserves_description_when_omitted(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_list = WordList(
            id=list_id,
            user_id=user_id,
            name="Original name",
            description="Keep me",
            created_at=datetime.now(timezone.utc),
        )
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = word_list
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, list_result, duplicate_result]

        response = await client.patch(
            f"/api/word-lists/{list_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Renamed"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"
        assert response.json()["description"] == "Keep me"
        assert word_list.description == "Keep me"

    @pytest.mark.asyncio
    async def test_update_word_list_rejects_duplicate_name(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing = WordList(
            id=list_id,
            user_id=user_id,
            name="Original",
            created_at=datetime.now(timezone.utc),
        )
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = existing
        duplicate_result = MagicMock()
        duplicate_result.scalar_one_or_none.return_value = WordList(
            id=uuid.uuid4(),
            user_id=user_id,
            name="Duplicate",
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.side_effect = [user_result, list_result, duplicate_result]

        response = await client.patch(
            f"/api/word-lists/{list_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Duplicate"},
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Word list name already exists"

    @pytest.mark.asyncio
    async def test_get_word_list_includes_primary_definition_and_translation(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        item_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        meaning_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = WordList(
            id=list_id,
            user_id=user_id,
            name="Learner list",
            created_at=datetime.now(timezone.utc),
        )
        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = [
            WordListItem(
                id=item_id,
                word_list_id=list_id,
                entry_type="word",
                entry_id=entry_id,
                frequency_count=2,
                added_at=datetime.now(timezone.utc),
            )
        ]
        catalog_row = MagicMock(
            entry_type="word",
            entry_id=entry_id,
            display_text="resilience",
            normalized_form="resilience",
            browse_rank=42,
            cefr_level="B2",
            phrase_kind=None,
            primary_part_of_speech="noun",
        )
        catalog_result = MagicMock()
        catalog_result.scalars.return_value.all.return_value = [catalog_row]
        status_result = MagicMock()
        status_result.scalars.return_value.all.return_value = []
        preferences_result = MagicMock()
        preferences_result.scalar_one_or_none.return_value = None
        primary_meaning = Meaning(id=meaning_id, word_id=entry_id, definition="The ability to recover quickly.", order_index=0)
        primary_meanings_result = MagicMock()
        primary_meanings_result.scalars.return_value.all.return_value = [primary_meaning]
        translations_result = MagicMock()
        translations_result.scalars.return_value.all.return_value = [
            Translation(id=uuid.uuid4(), meaning_id=meaning_id, language="zh-Hans", translation="韧性")
        ]
        mock_db.execute.side_effect = [
            user_result,
            list_result,
            item_result,
            catalog_result,
            status_result,
            preferences_result,
            primary_meanings_result,
            translations_result,
        ]

        response = await client.get(
            f"/api/word-lists/{list_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["display_text"] == "resilience"
        assert item["primary_definition"] == "The ability to recover quickly."
        assert item["translation"] == "韧性"

    @pytest.mark.asyncio
    async def test_bulk_delete_word_lists(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_one = WordList(id=uuid.uuid4(), user_id=user_id, name="One", created_at=datetime.now(timezone.utc))
        list_two = WordList(id=uuid.uuid4(), user_id=user_id, name="Two", created_at=datetime.now(timezone.utc))

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        lists_result = MagicMock()
        lists_result.scalars.return_value.all.return_value = [list_one, list_two]
        mock_db.execute.side_effect = [user_result, lists_result]

        response = await client.request(
            "DELETE",
            "/api/word-lists",
            headers={"Authorization": f"Bearer {token}"},
            json={"word_list_ids": [str(list_one.id), str(list_two.id)]},
        )

        assert response.status_code == 204
        assert mock_db.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_bulk_delete_word_list_items(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        item_one = WordListItem(
            id=uuid.uuid4(),
            word_list_id=list_id,
            entry_type="word",
            entry_id=uuid.uuid4(),
            frequency_count=1,
        )
        item_two = WordListItem(
            id=uuid.uuid4(),
            word_list_id=list_id,
            entry_type="phrase",
            entry_id=uuid.uuid4(),
            frequency_count=2,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = WordList(
            id=list_id,
            user_id=user_id,
            name="List",
            created_at=datetime.now(timezone.utc),
        )
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item_one, item_two]
        mock_db.execute.side_effect = [user_result, list_result, items_result]

        response = await client.request(
            "DELETE",
            f"/api/word-lists/{list_id}/items",
            headers={"Authorization": f"Bearer {token}"},
            json={"item_ids": [str(item_one.id), str(item_two.id)]},
        )

        assert response.status_code == 204
        assert mock_db.delete.await_count == 2

    @pytest.mark.asyncio
    async def test_get_word_list_includes_learner_status(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        entry_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        list_result = MagicMock()
        list_result.scalar_one_or_none.return_value = WordList(
            id=list_id,
            user_id=user_id,
            name="List",
            created_at=datetime.now(timezone.utc),
        )
        item = WordListItem(
            id=uuid.uuid4(),
            word_list_id=list_id,
            entry_type="word",
            entry_id=entry_id,
            frequency_count=2,
            added_at=datetime.now(timezone.utc),
        )
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        catalog_row = MagicMock(
            entry_type="word",
            entry_id=entry_id,
            display_text="resilience",
            normalized_form="resilience",
            browse_rank=100,
            cefr_level="B2",
            phrase_kind=None,
            primary_part_of_speech="noun",
        )
        catalog_result = MagicMock()
        catalog_result.scalars.return_value.all.return_value = [catalog_row]
        status_row = MagicMock(entry_type="word", entry_id=entry_id, status="learning")
        status_result = MagicMock()
        status_result.scalars.return_value.all.return_value = [status_row]
        preferences_result = MagicMock()
        preferences_result.scalar_one_or_none.return_value = None
        primary_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=entry_id,
            definition="The ability to recover quickly.",
            order_index=0,
        )
        primary_meanings_result = MagicMock()
        primary_meanings_result.scalars.return_value.all.return_value = [primary_meaning]
        translations_result = MagicMock()
        translations_result.scalars.return_value.all.return_value = [
            Translation(
                id=uuid.uuid4(),
                meaning_id=primary_meaning.id,
                language="zh-Hans",
                translation="韧性",
            )
        ]
        mock_db.execute.side_effect = [
            user_result,
            list_result,
            items_result,
            catalog_result,
            status_result,
            preferences_result,
            primary_meanings_result,
            translations_result,
        ]

        response = await client.get(
            f"/api/word-lists/{list_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["items"][0]["status"] == "learning"

    @pytest.mark.asyncio
    async def test_bulk_add_entries_returns_word_list_detail_with_explicit_query_defaults(
        self,
        client,
        mock_db,
        monkeypatch,
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        list_id = uuid.uuid4()
        entry_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        added_calls: list[tuple[uuid.UUID, str, uuid.UUID]] = []

        async def fake_add_word_list_item(*, word_list_id, request, current_user, db):
            assert current_user.id == user_id
            assert db is mock_db
            added_calls.append((word_list_id, request.entry_type, request.entry_id))
            return MagicMock()

        async def fake_get_word_list(*, word_list_id, q, sort, order, current_user, db):
            assert word_list_id == list_id
            assert q is None
            assert sort == "alpha"
            assert order == "asc"
            assert current_user.id == user_id
            assert db is mock_db
            return word_lists_api.WordListDetailResponse(
                id=str(list_id),
                user_id=str(user_id),
                name="Debug List",
                description=None,
                source_type=None,
                source_reference=None,
                created_at=datetime.now(timezone.utc),
                items=[],
            )

        monkeypatch.setattr(word_lists_api, "add_word_list_item", fake_add_word_list_item)
        monkeypatch.setattr(word_lists_api, "get_word_list", fake_get_word_list)

        response = await client.post(
            f"/api/word-lists/{list_id}/bulk-add",
            headers={"Authorization": f"Bearer {token}"},
            json={"selected_entries": [{"entry_type": "phrase", "entry_id": str(entry_id)}]},
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(list_id)
        assert added_calls == [(list_id, "phrase", entry_id)]
