import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.phrase_entry import PhraseEntry
from app.models.search_history import SearchHistory
from app.models.translation import Translation
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.models.word_relation import WordRelation


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


def scalars_all_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


class TestKnowledgeMapOverview:
    @pytest.mark.asyncio
    async def test_overview_returns_bucket_counts(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word_one = Word(id=uuid.uuid4(), word="bank", language="en", frequency_rank=20)
        word_two = Word(id=uuid.uuid4(), word="branch", language="en", frequency_rank=130)
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
        )
        statuses = [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_one.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="learning"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalars_all_result([word_one, word_two]),
            scalars_all_result([phrase]),
            scalars_all_result(statuses),
        ]

        response = await client.get(
            "/api/knowledge-map/overview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bucket_size"] == 100
        assert data["total_entries"] == 3
        assert len(data["ranges"]) == 2
        assert data["ranges"][0]["range_start"] == 1
        assert data["ranges"][0]["counts"]["known"] == 1
        assert data["ranges"][1]["counts"]["learning"] == 1


class TestKnowledgeMapDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_returns_summary_and_next_steps(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word_known = Word(id=uuid.uuid4(), word="the", language="en", frequency_rank=1)
        word_new = Word(id=uuid.uuid4(), word="resilience", language="en", frequency_rank=20)
        word_learning = Word(id=uuid.uuid4(), word="bank", language="en", frequency_rank=140)
        phrase_to_learn = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
        )
        statuses = [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_known.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_learning.id, status="learning"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase_to_learn.id, status="to_learn"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalars_all_result([word_known, word_new, word_learning]),
            scalars_all_result([phrase_to_learn]),
            scalars_all_result(statuses),
        ]

        response = await client.get(
            "/api/knowledge-map/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_entries"] == 4
        assert data["counts"] == {
            "undecided": 1,
            "to_learn": 1,
            "learning": 1,
            "known": 1,
        }
        assert data["discovery_range_start"] == 1
        assert data["discovery_range_end"] == 100
        assert data["discovery_entry"]["entry_type"] == "word"
        assert data["discovery_entry"]["display_text"] == "resilience"
        assert data["next_learn_entry"]["entry_type"] == "phrase"
        assert data["next_learn_entry"]["display_text"] == "bank on"


class TestKnowledgeMapRange:
    @pytest.mark.asyncio
    async def test_range_returns_mixed_entries(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, accent_preference="uk", translation_locale="es")
        word = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            frequency_rank=20,
            phonetic="/bæŋk/",
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/baŋk/", "confidence": 0.98},
            },
        )
        word_meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A financial institution", order_index=0)
        translation = Translation(id=uuid.uuid4(), meaning_id=word_meaning.id, language="es", translation="banco")
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
            compiled_payload={
                "senses": [
                    {
                        "definition": "To depend on someone.",
                        "translations": {"zh-Hans": {"definition": "依靠", "examples": [], "usage_note": "common"}},
                    }
                ]
            },
        )
        statuses = [LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="to_learn")]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalars_all_result([word]),
            scalars_all_result([phrase]),
            scalars_all_result(statuses),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_meaning]),
            scalars_all_result([translation]),
            scalars_all_result([word]),
        ]

        response = await client.get(
            "/api/knowledge-map/ranges/1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["range_start"] == 1
        assert len(data["items"]) == 2
        assert data["items"][0]["entry_type"] == "word"
        assert data["items"][0]["status"] == "to_learn"
        assert data["items"][0]["pronunciation"] == "/baŋk/"
        assert data["items"][0]["translation"] == "banco"
        assert data["items"][1]["entry_type"] == "phrase"


class TestKnowledgeMapList:
    @pytest.mark.asyncio
    async def test_list_filters_and_sorts_entries(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, accent_preference="uk", translation_locale="es")
        word_known = Word(id=uuid.uuid4(), word="the", language="en", frequency_rank=1)
        word_new = Word(id=uuid.uuid4(), word="resilience", language="en", frequency_rank=20)
        word_learning = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            frequency_rank=140,
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/baŋk/", "confidence": 0.98},
            },
        )
        word_new_meaning = Meaning(id=uuid.uuid4(), word_id=word_new.id, definition="Resilience definition", order_index=0)
        word_learning_meaning = Meaning(id=uuid.uuid4(), word_id=word_learning.id, definition="Bank definition", order_index=0)
        word_new_translation = Translation(
            id=uuid.uuid4(),
            meaning_id=word_new_meaning.id,
            language="es",
            translation="resiliencia",
        )
        word_learning_translation = Translation(
            id=uuid.uuid4(),
            meaning_id=word_learning_meaning.id,
            language="es",
            translation="banco",
        )
        phrase_to_learn = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
        )
        statuses = [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_known.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_learning.id, status="learning"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase_to_learn.id, status="to_learn"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalars_all_result([word_known, word_new, word_learning]),
            scalars_all_result([phrase_to_learn]),
            scalars_all_result(statuses),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_new_meaning]),
            scalars_all_result([word_new_translation]),
            scalars_all_result([word_new]),
            scalar_one_or_none_result(user),
            scalars_all_result([word_known, word_new, word_learning]),
            scalars_all_result([phrase_to_learn]),
            scalars_all_result(statuses),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_learning_meaning]),
            scalars_all_result([word_learning_translation]),
            scalars_all_result([word_learning]),
            scalar_one_or_none_result(user),
            scalars_all_result([word_known, word_new, word_learning]),
            scalars_all_result([phrase_to_learn]),
            scalars_all_result(statuses),
        ]

        new_response = await client.get(
            "/api/knowledge-map/list?status=new&sort=rank",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert new_response.status_code == 200
        assert [item["display_text"] for item in new_response.json()["items"]] == ["resilience"]
        assert new_response.json()["items"][0]["translation"] == "resiliencia"

        learning_response = await client.get(
            "/api/knowledge-map/list?status=learning&sort=alpha",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert learning_response.status_code == 200
        assert [item["display_text"] for item in learning_response.json()["items"]] == ["bank"]
        assert learning_response.json()["items"][0]["pronunciation"] == "/baŋk/"
        assert learning_response.json()["items"][0]["primary_definition"] == "Bank definition"

        search_response = await client.get(
            "/api/knowledge-map/list?status=to_learn&q=bank&sort=rank_desc",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert search_response.status_code == 200
        payload = search_response.json()
        assert [item["display_text"] for item in payload["items"]] == ["bank on"]


class TestKnowledgeMapDetail:
    @pytest.mark.asyncio
    async def test_word_detail_uses_preferences(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, accent_preference="uk", translation_locale="es")
        word = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            frequency_rank=20,
            phonetic="/bæŋk/",
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/baŋk/", "confidence": 0.98},
            },
            confusable_words=[
                {"word": "bench", "note": "Different object."},
                {"word": " bench ", "note": "  "},
                {"word": "banque", "note": "Foreign-language lookalike."},
                {"note": "Missing word."},
                "invalid",
                {"word": "   ", "note": "Blank word."},
            ],
        )
        meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A financial institution", order_index=0)
        translation = Translation(id=uuid.uuid4(), meaning_id=meaning.id, language="es", translation="banco")
        relation = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="synonym",
            related_word="lender",
        )
        relation_duplicate = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type=" Synonym ",
            related_word=" lender ",
        )
        relation_mixed_case = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="SYNONYM",
            related_word="LENDER",
        )
        relation_proper_noun = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="Synonym",
            related_word="iPhone",
        )
        relation_proper_noun_duplicate = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type=" synonym ",
            related_word="iphone",
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="learning")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(word),
            scalars_all_result([meaning]),
            scalars_all_result([]),
            scalars_all_result([translation]),
            scalars_all_result(
                [
                    relation,
                    relation_duplicate,
                    relation_mixed_case,
                    relation_proper_noun,
                    relation_proper_noun_duplicate,
                ]
            ),
            scalars_all_result([word]),
            scalars_all_result([]),
            scalar_one_or_none_result(status),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/word/{word.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entry_type"] == "word"
        assert data["status"] == "learning"
        assert data["pronunciation"] == "/baŋk/"
        assert data["translation"] == "banco"
        assert data["confusable_words"] == [
            {"word": "bench", "note": "Different object."},
            {"word": "bench", "note": None},
            {"word": "banque", "note": "Foreign-language lookalike."},
        ]
        assert data["relation_groups"] == [
            {"relation_type": "synonym", "related_words": ["lender", "iPhone"]},
        ]
        assert len(data["meanings"][0]["relations"]) == 5
        assert {item["relation_type"] for item in data["meanings"][0]["relations"]} == {
            "synonym",
            " Synonym ",
            "SYNONYM",
            "Synonym",
            " synonym ",
        }

    @pytest.mark.asyncio
    async def test_phrase_detail_reads_compiled_payload(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, translation_locale="zh-Hans")
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
            compiled_payload={
                "senses": [
                    {
                        "definition": "To rely on someone.",
                        "examples": [{"sentence": "You can bank on me.", "difficulty": "B1"}],
                        "translations": {"zh-Hans": {"definition": "依靠", "examples": ["你可以依靠我。"], "usage_note": "common"}},
                    }
                ]
            },
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="known")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(phrase),
            scalar_one_or_none_result(status),
            scalars_all_result([]),
            scalars_all_result([phrase]),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/phrase/{phrase.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entry_type"] == "phrase"
        assert data["status"] == "known"
        assert data["translation"] == "依靠"
        assert data["senses"][0]["definition"] == "To rely on someone."
        assert data["relation_groups"] == []
        assert data["confusable_words"] == []


class TestKnowledgeMapStatus:
    @pytest.mark.asyncio
    async def test_put_status_upserts_status(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = Word(id=uuid.uuid4(), word="bank", language="en", frequency_rank=20)

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(word),
            scalar_one_or_none_result(None),
        ]

        response = await client.put(
            f"/api/knowledge-map/entries/word/{word.id}/status",
            json={"status": "known"},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entry_type"] == "word"
        assert data["entry_id"] == str(word.id)
        assert data["status"] == "known"


class TestKnowledgeMapSearchAndHistory:
    @pytest.mark.asyncio
    async def test_search_returns_mixed_entries(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, accent_preference="uk", translation_locale="es")
        word = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            frequency_rank=20,
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/baŋk/", "confidence": 0.98},
            },
        )
        meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A financial institution", order_index=0)
        translation = Translation(id=uuid.uuid4(), meaning_id=meaning.id, language="es", translation="banco")
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="learning")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalars_all_result([word]),
            scalars_all_result([phrase]),
            scalars_all_result([status]),
            scalar_one_or_none_result(preferences),
            scalars_all_result([meaning]),
            scalars_all_result([translation]),
            scalars_all_result([word]),
        ]

        response = await client.get(
            "/api/knowledge-map/search?q=bank",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["display_text"] == "bank"
        assert data["items"][0]["pronunciation"] == "/baŋk/"
        assert data["items"][0]["translation"] == "banco"
        assert data["items"][0]["primary_definition"] == "A financial institution"

    @pytest.mark.asyncio
    async def test_search_history_round_trip(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        history_row = SearchHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            query="bank",
            entry_type="word",
            entry_id=uuid.uuid4(),
            last_searched_at=datetime.now(timezone.utc),
        )

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(None),
            scalar_one_or_none_result(user),
            scalars_all_result([history_row]),
        ]

        create_response = await client.post(
            "/api/knowledge-map/search-history",
            json={"query": "bank", "entry_type": "word", "entry_id": str(history_row.entry_id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_response.status_code == 201

        list_response = await client.get(
            "/api/knowledge-map/search-history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["items"][0]["query"] == "bank"
