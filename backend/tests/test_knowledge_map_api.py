import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.api.request_db_metrics import instrument_session_for_request, restore_session_after_request
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization
from app.models.phrase_sense_localization import PhraseSenseLocalization
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
    session.info = {}
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    return r


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


def mappings_all_result(values):
    result = MagicMock()
    result.mappings.return_value.all.return_value = values
    result.mappings.return_value.one_or_none.return_value = values[0] if len(values) == 1 else None
    return result


def mappings_one_result(value):
    result = MagicMock()
    result.mappings.return_value.one.return_value = value
    return result


class TestKnowledgeMapOverview:
    @pytest.mark.asyncio
    async def test_overview_emits_learner_query_metrics_headers(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result([]),
        ]

        response = await client.get(
            "/api/knowledge-map/overview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["X-Knowledge-Map-Query-Count"] == "2"
        assert float(response.headers["X-Knowledge-Map-Query-Time-Ms"]) >= 0.0

    @pytest.mark.asyncio
    async def test_overview_returns_bucket_counts(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word_one = Word(id=uuid.uuid4(), word="bank", language="en", frequency_rank=20)
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
                        "translations": {"es": {"definition": "contar con", "examples": [], "usage_note": None}},
                    }
                ]
            },
        )
        [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_one.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="learning"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "range_start": 1,
                        "status": "known",
                        "entry_count": 1,
                    },
                    {
                        "range_start": 101,
                        "status": "undecided",
                        "entry_count": 1,
                    },
                    {
                        "range_start": 101,
                        "status": "learning",
                        "entry_count": 1,
                    },
                ]
            ),
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
        [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_known.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_learning.id, status="learning"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase_to_learn.id, status="to_learn"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "status": "known",
                        "entry_count": 1,
                    },
                    {
                        "status": "undecided",
                        "entry_count": 1,
                    },
                    {
                        "status": "learning",
                        "entry_count": 1,
                    },
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase_to_learn.id,
                        "display_text": "bank on",
                        "status": "to_learn",
                        "entry_count": 1,
                    },
                ]
            ),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word_new.id,
                        "display_text": "resilience",
                        "browse_rank": 20,
                        "status": "undecided",
                    }
                ]
            ),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase_to_learn.id,
                        "display_text": "bank on",
                        "browse_rank": 141,
                        "status": "to_learn",
                    }
                ]
            ),
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
    async def test_range_returns_phrase_only_entries_with_definition_and_translation(
        self, client, mock_db, auth_token
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, translation_locale="es")
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
            compiled_payload={
                "senses": [
                    {
                        "definition": "stale compiled definition",
                        "translations": {"es": {"definition": "stale compiled translation"}},
                    }
                ]
            },
        )
        sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="To depend on someone.",
            usage_note=None,
            order_index=0,
        )
        sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=sense.id,
            locale="es",
            localized_definition="contar con",
            localized_usage_note="common",
        )

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "normalized_form": "bank on",
                        "browse_rank": 1,
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": "phrasal_verb",
                    }
                ]
            ),
            mappings_one_result({"previous_rank": None, "next_rank": None}),
            scalars_all_result([]),
            scalar_one_or_none_result(preferences),
            scalars_all_result([sense]),
            scalars_all_result([sense_localization]),
        ]

        response = await client.get(
            "/api/knowledge-map/ranges/1",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == [
            {
                "entry_type": "phrase",
                "entry_id": str(phrase.id),
                "display_text": "bank on",
                "normalized_form": "bank on",
                "browse_rank": 1,
                "status": "undecided",
                "cefr_level": None,
                "pronunciation": None,
                "translation": "contar con",
                "primary_definition": "To depend on someone.",
                "part_of_speech": None,
                "phrase_kind": "phrasal_verb",
            }
        ]

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
                        "translations": {
                            "es": {
                                "definition": "contar con",
                                "examples": [],
                                "usage_note": "common",
                            }
                        },
                    }
                ]
            },
        )
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="To depend on someone.",
            usage_note=None,
            order_index=0,
        )
        phrase_sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            locale="es",
            localized_definition="contar con",
            localized_usage_note="common",
        )
        statuses = [LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="to_learn")]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "bank",
                        "normalized_form": "bank",
                        "browse_rank": 20,
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": None,
                    },
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "normalized_form": "bank on",
                        "browse_rank": 21,
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": "phrasal_verb",
                    },
                ]
            ),
            mappings_one_result({"previous_rank": None, "next_rank": None}),
            scalars_all_result(statuses),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_meaning]),
            scalars_all_result([translation]),
            scalars_all_result([word]),
            scalars_all_result([phrase_sense]),
            scalars_all_result([phrase_sense_localization]),
            scalars_all_result([]),
            scalars_all_result([]),
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
        assert data["items"][1]["primary_definition"] == "To depend on someone."
        assert data["items"][1]["translation"] == "contar con"


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
            compiled_payload={
                "senses": [
                    {
                        "definition": "stale compiled definition",
                        "translations": {"es": {"definition": "stale compiled translation"}},
                    }
                ]
            },
        )
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase_to_learn.id,
            definition="To depend on someone.",
            usage_note=None,
            order_index=0,
        )
        phrase_sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            locale="es",
            localized_definition="contar con",
            localized_usage_note="common",
        )
        [
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_known.id, status="known"),
            LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word_learning.id, status="learning"),
            LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase_to_learn.id, status="to_learn"),
        ]

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word_new.id,
                        "display_text": "resilience",
                        "normalized_form": "resilience",
                        "browse_rank": 20,
                        "status": "undecided",
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": None,
                    }
                ]
            ),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_new_meaning]),
            scalars_all_result([word_new_translation]),
            scalars_all_result([word_new]),
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word_learning.id,
                        "display_text": "bank",
                        "normalized_form": "bank",
                        "browse_rank": 140,
                        "status": "learning",
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": None,
                    }
                ]
            ),
            scalar_one_or_none_result(preferences),
            scalars_all_result([word_learning_meaning]),
            scalars_all_result([word_learning_translation]),
            scalars_all_result([word_learning]),
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase_to_learn.id,
                        "display_text": "bank on",
                        "normalized_form": "bank on",
                        "browse_rank": 141,
                        "status": "to_learn",
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": "phrasal_verb",
                    }
                ]
            ),
            scalar_one_or_none_result(preferences),
            scalars_all_result([phrase_sense]),
            scalars_all_result([phrase_sense_localization]),
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
        assert payload["items"][0]["primary_definition"] == "To depend on someone."
        assert payload["items"][0]["translation"] == "contar con"


class TestKnowledgeMapDetail:
    @pytest.mark.asyncio
    async def test_word_detail_supports_projection_catalog_rows(self, client, mock_db, auth_token):
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
        word.part_of_speech_entries = [MagicMock(value="noun", order_index=0)]
        word.form_entries = [MagicMock(form_kind="derivation", form_slot=None, value="lender", order_index=0)]
        meaning = Meaning(id=uuid.uuid4(), word_id=word.id, definition="A financial institution", order_index=0)
        translation = Translation(id=uuid.uuid4(), meaning_id=meaning.id, language="es", translation="banco")
        word_status = LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="learning")
        lender_id = uuid.uuid4()
        phrase_id = uuid.uuid4()

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(word),
            scalars_all_result([meaning]),
            scalars_all_result([]),
            scalars_all_result([translation]),
            scalars_all_result([]),
            scalar_one_or_none_result(word_status),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "bank",
                        "browse_rank": 20,
                        "status": "learning",
                        "cefr_level": None,
                    },
                ]
            ),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": lender_id,
                        "display_text": "lender",
                        "browse_rank": 30,
                        "status": "undecided",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result(
                [
                    {
                        "id": lender_id,
                        "word": "lender",
                        "frequency_rank": 30,
                        "cefr_level": None,
                        "learner_part_of_speech": "noun",
                    }
                ]
            ),
            mappings_all_result(
                [
                    {
                        "id": phrase_id,
                        "phrase_text": "bank on",
                        "normalized_form": "bank on",
                        "cefr_level": None,
                        "phrase_kind": "phrasal_verb",
                    }
                ]
            ),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/word/{word.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["browse_rank"] == 20
        assert data["status"] == "learning"
        assert data["pronunciation"] == "/baŋk/"
        assert data["translation"] == "banco"
        assert data["next_entry"]["entry_id"] == str(lender_id)
        assert data["forms"]["derivations"] == [
            {
                "text": "lender",
                "target": {
                    "entry_type": "word",
                    "entry_id": str(lender_id),
                    "display_text": "lender",
                },
            }
        ]

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
        )
        word.part_of_speech_entries = [MagicMock(value="noun", order_index=0)]
        word.confusable_entries = [
            MagicMock(confusable_word="bench", note="Different object.", order_index=0),
            MagicMock(confusable_word="bench", note=None, order_index=1),
            MagicMock(confusable_word="banque", note="Foreign-language lookalike.", order_index=2),
            MagicMock(confusable_word="", note="Blank word.", order_index=3),
        ]
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
            scalar_one_or_none_result(status),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "bank",
                        "browse_rank": 20,
                        "status": "learning",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result([]),
            mappings_all_result([]),
            mappings_all_result([]),
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
            {"word": "bench", "note": "Different object.", "target": None},
            {"word": "bench", "note": None, "target": None},
            {"word": "banque", "note": "Foreign-language lookalike.", "target": None},
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
    async def test_word_detail_returns_schema_aligned_translations_forms_and_related_links(
        self, client, mock_db, auth_token
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, accent_preference="uk", translation_locale="pt-BR")
        word = Word(
            id=uuid.uuid4(),
            word="time",
            language="en",
            frequency_rank=60,
            phonetics={
                "uk": {"ipa": "taɪm", "confidence": 0.96},
                "us": {"ipa": "taɪm", "confidence": 0.96},
            },
        )
        word.part_of_speech_entries = [MagicMock(value="noun", order_index=0)]
        word.form_entries = [
            MagicMock(form_kind="verb", form_slot="base", value="time", order_index=0),
            MagicMock(form_kind="verb", form_slot="past", value="timed", order_index=1),
            MagicMock(form_kind="verb", form_slot="gerund", value="timing", order_index=2),
            MagicMock(form_kind="verb", form_slot="past_participle", value="timed", order_index=3),
            MagicMock(form_kind="verb", form_slot="third_person_singular", value="times", order_index=4),
            MagicMock(form_kind="plural", form_slot=None, value="times", order_index=0),
            MagicMock(form_kind="derivation", form_slot=None, value="timely", order_index=0),
            MagicMock(form_kind="derivation", form_slot=None, value="timing", order_index=1),
        ]
        word.confusable_entries = [
            MagicMock(confusable_word="clock", note="Device rather than duration.", order_index=0),
        ]
        meaning = Meaning(
            id=uuid.uuid4(),
            word_id=word.id,
            definition="the thing measured in minutes and hours",
            part_of_speech="noun",
            primary_domain="general",
            register_label="neutral",
            usage_note="Common in both abstract and practical contexts.",
            order_index=0,
        )
        meaning.metadata_entries = [
            MagicMock(metadata_kind="secondary_domain", value="society", order_index=0),
            MagicMock(metadata_kind="grammar_pattern", value="have time", order_index=0),
            MagicMock(metadata_kind="grammar_pattern", value="time for + noun", order_index=1),
        ]
        example = MeaningExample(
            id=uuid.uuid4(),
            meaning_id=meaning.id,
            sentence="I do not have time today.",
            difficulty="A1",
            order_index=0,
        )
        translation = Translation(
            id=uuid.uuid4(),
            meaning_id=meaning.id,
            language="pt-BR",
            translation="tempo",
        )
        setattr(translation, "usage_note", "Muito comum em contextos abstratos e práticos.")
        setattr(translation, "examples", ["stale translated example"])
        translation.example_entries = [MagicMock(text="Eu não tenho tempo hoje.", order_index=0)]
        synonym = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="synonym",
            related_word="duration",
        )
        antonym = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="antonym",
            related_word="timelessness",
        )
        collocation = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="collocation",
            related_word="have time",
        )
        linked_word = Word(id=uuid.uuid4(), word="duration", language="en", frequency_rank=500)
        linked_phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="have time",
            normalized_form="have time",
            phrase_kind="phrase",
            language="en",
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="to_learn")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(word),
            scalars_all_result([meaning]),
            scalars_all_result([example]),
            scalars_all_result([translation]),
            scalars_all_result([synonym, antonym, collocation]),
            scalar_one_or_none_result(status),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "time",
                        "browse_rank": 60,
                        "status": "to_learn",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result([]),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "time",
                        "normalized_form": "time",
                        "browse_rank": 60,
                    },
                    {
                        "entry_type": "word",
                        "entry_id": linked_word.id,
                        "display_text": "duration",
                        "normalized_form": "duration",
                        "browse_rank": 500,
                    },
                    {
                        "entry_type": "phrase",
                        "entry_id": linked_phrase.id,
                        "display_text": "have time",
                        "normalized_form": "have time",
                        "browse_rank": 1001,
                    },
                ]
            ),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/word/{word.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pronunciation"] == "taɪm"
        assert data["translation"] == "tempo"
        assert data["forms"]["verb_forms"]["past"] == "timed"
        assert data["forms"]["plural_forms"] == ["times"]
        assert data["forms"]["derivations"][0]["text"] == "timely"
        assert data["forms"]["comparative"] is None
        assert data["forms"]["superlative"] is None
        assert data["meanings"][0]["localized_definition"] == "tempo"
        assert data["meanings"][0]["localized_usage_note"] == "Muito comum em contextos abstratos e práticos."
        assert data["meanings"][0]["usage_note"] == "Common in both abstract and practical contexts."
        assert data["meanings"][0]["grammar_patterns"] == ["have time", "time for + noun"]
        assert data["meanings"][0]["register"] == "neutral"
        assert data["meanings"][0]["primary_domain"] == "general"
        assert data["meanings"][0]["secondary_domains"] == ["society"]
        assert data["meanings"][0]["examples"][0]["translation"] == "Eu não tenho tempo hoje."
        assert data["meanings"][0]["translations"][0]["examples"] == ["Eu não tenho tempo hoje."]
        assert data["meanings"][0]["examples"][0]["linked_entries"] == [
            {
                "text": "time",
                "entry_type": "word",
                "entry_id": str(word.id),
            }
        ]
        assert data["meanings"][0]["synonyms"][0] == {
            "text": "duration",
            "target": {
                "entry_type": "word",
                "entry_id": str(linked_word.id),
                "display_text": "duration",
            },
        }
        assert data["meanings"][0]["collocations"][0] == {
            "text": "have time",
            "target": {
                "entry_type": "phrase",
                "entry_id": str(linked_phrase.id),
                "display_text": "have time",
            },
        }
        assert data["confusable_words"][0]["target"] is None

    @pytest.mark.asyncio
    async def test_phrase_detail_uses_normalized_metadata(self, client, mock_db, auth_token):
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
                        "definition": "To depend on someone.",
                        "usage_note": "Often used in spoken English.",
                        "pos": "noun",
                        "register": "formal",
                        "primary_domain": "finance",
                        "secondary_domains": ["banking"],
                        "grammar_patterns": ["compiled-only pattern"],
                        "synonyms": ["compiled synonym"],
                        "antonyms": ["compiled antonym"],
                        "collocations": ["compiled collocation"],
                        "examples": [{"sentence": "stale compiled sentence", "difficulty": "B1"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "依赖",
                                "usage_note": "常用于口语。",
                                "examples": ["stale compiled example translation"],
                            }
                        },
                    }
                ]
            },
        )
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="To depend on someone.",
            usage_note="Often used in spoken English.",
            part_of_speech="phrasal_verb",
            register="neutral",
            primary_domain="general",
            secondary_domains=["finance"],
            grammar_patterns=["bank on + noun"],
            synonyms=["depend on"],
            antonyms=["distrust"],
            collocations=["bank on it"],
            order_index=0,
        )
        phrase_sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            locale="zh-Hans",
            localized_definition="依赖",
            localized_usage_note="常用于口语。",
        )
        phrase_example = PhraseSenseExample(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            sentence="You can bank on me.",
            difficulty="B1",
            order_index=0,
        )
        phrase_example_localization = PhraseSenseExampleLocalization(
            id=uuid.uuid4(),
            phrase_sense_example_id=phrase_example.id,
            locale="zh-Hans",
            translation="你可以指望我。",
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="known")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(phrase),
            scalar_one_or_none_result(status),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "browse_rank": 141,
                        "status": "known",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result([]),
            scalars_all_result([phrase_sense]),
            scalars_all_result([phrase_sense_localization]),
            scalars_all_result([phrase_example]),
            scalars_all_result([phrase_example_localization]),
            mappings_all_result([]),
            mappings_all_result([]),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/phrase/{phrase.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entry_type"] == "phrase"
        assert data["status"] == "known"
        assert data["translation"] == "依赖"
        assert data["primary_definition"] == "To depend on someone."
        assert data["senses"][0]["definition"] == "To depend on someone."
        assert data["senses"][0]["localized_definition"] == "依赖"
        assert data["senses"][0]["localized_usage_note"] == "常用于口语。"
        assert data["senses"][0]["part_of_speech"] == "phrasal_verb"
        assert data["senses"][0]["register"] == "neutral"
        assert data["senses"][0]["primary_domain"] == "general"
        assert data["senses"][0]["secondary_domains"] == ["finance"]
        assert data["senses"][0]["grammar_patterns"] == ["bank on + noun"]
        assert data["senses"][0]["synonyms"][0]["text"] == "depend on"
        assert data["senses"][0]["antonyms"][0]["text"] == "distrust"
        assert data["senses"][0]["collocations"][0]["text"] == "bank on it"
        assert data["senses"][0]["examples"][0]["translation"] == "你可以指望我。"
        assert data["senses"][0]["examples"][0]["sentence"] == "You can bank on me."
        assert data["relation_groups"] == []
        assert data["confusable_words"] == []

    @pytest.mark.asyncio
    async def test_phrase_detail_returns_localized_examples_usage_notes_and_exact_links(
        self, client, mock_db, auth_token
    ):
        token, user_id = auth_token
        user = make_user(user_id)
        preferences = UserPreference(user_id=user_id, translation_locale="ja")
        phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="bank on",
            normalized_form="bank on",
            phrase_kind="phrasal_verb",
            language="en",
            compiled_payload={
                "senses": [
                    {
                        "sense_id": "sense-1",
                        "definition": "To rely on someone.",
                        "pos": "noun",
                        "register": "formal",
                        "primary_domain": "finance",
                        "secondary_domains": ["banking"],
                        "usage_note": "Compiled note only.",
                        "grammar_patterns": ["compiled-only pattern"],
                        "synonyms": ["compiled synonym"],
                        "antonyms": ["compiled antonym"],
                        "collocations": ["compiled collocation"],
                        "examples": [{"sentence": "You can bank on support from me.", "difficulty": "B1"}],
                        "translations": {
                            "ja": {
                                "definition": "頼りにする",
                                "usage_note": "話し言葉でよく使われる。",
                                "examples": ["私の支援を頼りにしていい。"],
                            }
                        },
                    }
                ]
            },
        )
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="To rely on someone.",
            usage_note="Often used in spoken English.",
            part_of_speech="phrasal_verb",
            register="neutral",
            primary_domain="general",
            secondary_domains=["relationships"],
            grammar_patterns=["bank on + noun", "bank on + someone"],
            synonyms=["depend on"],
            antonyms=["doubt"],
            collocations=["bank on support"],
            order_index=0,
        )
        phrase_sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            locale="ja",
            localized_definition="頼りにする",
            localized_usage_note="話し言葉でよく使われる。",
        )
        phrase_example = PhraseSenseExample(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            sentence="You can bank on support from me.",
            difficulty="B1",
            order_index=0,
        )
        phrase_example_localization = PhraseSenseExampleLocalization(
            id=uuid.uuid4(),
            phrase_sense_example_id=phrase_example.id,
            locale="ja",
            translation="私の支援を頼りにしていい。",
        )
        linked_phrase = PhraseEntry(
            id=uuid.uuid4(),
            phrase_text="depend on",
            normalized_form="depend on",
            phrase_kind="phrasal_verb",
            language="en",
        )
        linked_word = Word(id=uuid.uuid4(), word="support", language="en", frequency_rank=320)
        status = LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="known")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(phrase),
            scalar_one_or_none_result(status),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "browse_rank": 141,
                        "status": "known",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result([]),
            scalars_all_result([phrase_sense]),
            scalars_all_result([phrase_sense_localization]),
            scalars_all_result([phrase_example]),
            scalars_all_result([phrase_example_localization]),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": linked_word.id,
                        "display_text": "support",
                        "normalized_form": "support",
                        "browse_rank": 320,
                    },
                    {
                        "entry_type": "phrase",
                        "entry_id": linked_phrase.id,
                        "display_text": "depend on",
                        "normalized_form": "depend on",
                        "browse_rank": 1001,
                    }
                ]
            ),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/phrase/{phrase.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["translation"] == "頼りにする"
        assert data["senses"][0]["localized_definition"] == "頼りにする"
        assert data["senses"][0]["localized_usage_note"] == "話し言葉でよく使われる。"
        assert data["senses"][0]["part_of_speech"] == "phrasal_verb"
        assert data["senses"][0]["register"] == "neutral"
        assert data["senses"][0]["primary_domain"] == "general"
        assert data["senses"][0]["secondary_domains"] == ["relationships"]
        assert data["senses"][0]["grammar_patterns"] == ["bank on + noun", "bank on + someone"]
        assert data["senses"][0]["examples"][0]["translation"] == "私の支援を頼りにしていい。"
        assert data["senses"][0]["examples"][0]["linked_entries"] == [
            {
                "text": "support",
                "entry_type": "word",
                "entry_id": str(linked_word.id),
            }
        ]
        assert data["senses"][0]["synonyms"] == [
            {
                "text": "depend on",
                "target": {
                    "entry_type": "phrase",
                    "entry_id": str(linked_phrase.id),
                    "display_text": "depend on",
                },
            }
        ]
        assert data["senses"][0]["antonyms"] == [
            {
                "text": "doubt",
                "target": None,
            }
        ]
        assert data["senses"][0]["collocations"] == [
            {
                "text": "bank on support",
                "target": None,
            }
        ]
        assert data["relation_groups"] == []

    @pytest.mark.asyncio
    async def test_phrase_detail_uses_normalized_metadata_by_sense_content_not_position(
        self, client, mock_db, auth_token
    ):
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
                        "definition": "Later normalized sense",
                        "usage_note": "Later compiled note",
                        "pos": "noun",
                        "register": "formal",
                        "primary_domain": "finance",
                        "secondary_domains": ["banking"],
                        "grammar_patterns": ["later compiled pattern"],
                        "synonyms": ["later compiled synonym"],
                        "antonyms": ["later compiled antonym"],
                        "collocations": ["later compiled collocation"],
                        "examples": [{"sentence": "Later compiled example.", "difficulty": "B1"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "后一个含义",
                                "usage_note": "后一个注释",
                                "examples": ["后一个例句。"],
                            }
                        },
                    },
                    {
                        "definition": "Earlier normalized sense",
                        "usage_note": "Earlier compiled note",
                        "pos": "verb",
                        "register": "neutral",
                        "primary_domain": "general",
                        "secondary_domains": ["practice"],
                        "grammar_patterns": ["earlier compiled pattern"],
                        "synonyms": ["earlier compiled synonym"],
                        "antonyms": ["earlier compiled antonym"],
                        "collocations": ["earlier compiled collocation"],
                        "examples": [{"sentence": "Earlier compiled example.", "difficulty": "B1"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "前一个含义",
                                "usage_note": "前一个注释",
                                "examples": ["前一个例句。"],
                            }
                        },
                    },
                ]
            },
        )
        later_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="Later normalized sense",
            usage_note="Later compiled note",
            part_of_speech="noun",
            register="formal",
            primary_domain="finance",
            secondary_domains=["banking"],
            grammar_patterns=["later compiled pattern"],
            synonyms=["later compiled synonym"],
            antonyms=["later compiled antonym"],
            collocations=["later compiled collocation"],
            order_index=1,
        )
        earlier_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="Earlier normalized sense",
            usage_note="Earlier compiled note",
            part_of_speech="verb",
            register="neutral",
            primary_domain="general",
            secondary_domains=["practice"],
            grammar_patterns=["earlier compiled pattern"],
            synonyms=["earlier compiled synonym"],
            antonyms=["earlier compiled antonym"],
            collocations=["earlier compiled collocation"],
            order_index=0,
        )
        later_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=later_sense.id,
            locale="zh-Hans",
            localized_definition="后一个含义",
            localized_usage_note="后一个注释",
        )
        earlier_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=earlier_sense.id,
            locale="zh-Hans",
            localized_definition="前一个含义",
            localized_usage_note="前一个注释",
        )
        later_example = PhraseSenseExample(
            id=uuid.uuid4(),
            phrase_sense_id=later_sense.id,
            sentence="Later normalized example.",
            difficulty="B1",
            order_index=0,
        )
        earlier_example = PhraseSenseExample(
            id=uuid.uuid4(),
            phrase_sense_id=earlier_sense.id,
            sentence="Earlier normalized example.",
            difficulty="B1",
            order_index=0,
        )
        later_example_localization = PhraseSenseExampleLocalization(
            id=uuid.uuid4(),
            phrase_sense_example_id=later_example.id,
            locale="zh-Hans",
            translation="后一个例句。",
        )
        earlier_example_localization = PhraseSenseExampleLocalization(
            id=uuid.uuid4(),
            phrase_sense_example_id=earlier_example.id,
            locale="zh-Hans",
            translation="前一个例句。",
        )
        status = LearnerEntryStatus(user_id=user_id, entry_type="phrase", entry_id=phrase.id, status="known")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            scalar_one_or_none_result(preferences),
            scalar_one_or_none_result(phrase),
            scalar_one_or_none_result(status),
            mappings_all_result(
                [
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "browse_rank": 141,
                        "status": "known",
                        "cefr_level": None,
                    }
                ]
            ),
            mappings_all_result([]),
            scalars_all_result([earlier_sense, later_sense]),
            scalars_all_result([earlier_localization, later_localization]),
            scalars_all_result([earlier_example, later_example]),
            scalars_all_result([earlier_example_localization, later_example_localization]),
            mappings_all_result([]),
            mappings_all_result([]),
        ]

        response = await client.get(
            f"/api/knowledge-map/entries/phrase/{phrase.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["senses"][0]["definition"] == "Earlier normalized sense"
        assert data["senses"][0]["part_of_speech"] == "verb"
        assert data["senses"][0]["register"] == "neutral"
        assert data["senses"][0]["primary_domain"] == "general"
        assert data["senses"][0]["secondary_domains"] == ["practice"]
        assert data["senses"][0]["grammar_patterns"] == ["earlier compiled pattern"]
        assert data["senses"][0]["synonyms"][0]["text"] == "earlier compiled synonym"
        assert data["senses"][0]["antonyms"][0]["text"] == "earlier compiled antonym"
        assert data["senses"][0]["collocations"][0]["text"] == "earlier compiled collocation"
        assert data["senses"][0]["examples"][0]["translation"] == "前一个例句。"
        assert data["senses"][1]["definition"] == "Later normalized sense"
        assert data["senses"][1]["part_of_speech"] == "noun"
        assert data["senses"][1]["register"] == "formal"
        assert data["senses"][1]["primary_domain"] == "finance"
        assert data["senses"][1]["secondary_domains"] == ["banking"]
        assert data["senses"][1]["grammar_patterns"] == ["later compiled pattern"]
        assert data["senses"][1]["synonyms"][0]["text"] == "later compiled synonym"
        assert data["senses"][1]["antonyms"][0]["text"] == "later compiled antonym"
        assert data["senses"][1]["collocations"][0]["text"] == "later compiled collocation"
        assert data["senses"][1]["examples"][0]["translation"] == "后一个例句。"


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
            compiled_payload={
                "senses": [
                    {
                        "definition": "To depend on someone.",
                        "translations": {"es": {"definition": "contar con", "examples": [], "usage_note": None}},
                    }
                ]
            },
        )
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="To depend on someone.",
            usage_note=None,
            order_index=0,
        )
        phrase_sense_localization = PhraseSenseLocalization(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            locale="es",
            localized_definition="contar con",
            localized_usage_note="common",
        )
        LearnerEntryStatus(user_id=user_id, entry_type="word", entry_id=word.id, status="learning")

        mock_db.execute.side_effect = [
            scalar_one_or_none_result(user),
            mappings_all_result(
                [
                    {
                        "entry_type": "word",
                        "entry_id": word.id,
                        "display_text": "bank",
                        "normalized_form": "bank",
                        "browse_rank": 20,
                        "status": "learning",
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": None,
                    },
                    {
                        "entry_type": "phrase",
                        "entry_id": phrase.id,
                        "display_text": "bank on",
                        "normalized_form": "bank on",
                        "browse_rank": 21,
                        "status": "undecided",
                        "cefr_level": None,
                        "learner_part_of_speech": None,
                        "phrase_kind": "phrasal_verb",
                    },
                ]
            ),
            scalar_one_or_none_result(preferences),
            scalars_all_result([meaning]),
            scalars_all_result([translation]),
            scalars_all_result([word]),
            scalars_all_result([phrase_sense]),
            scalars_all_result([phrase_sense_localization]),
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
        assert data["items"][1]["display_text"] == "bank on"
        assert data["items"][1]["translation"] == "contar con"

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
