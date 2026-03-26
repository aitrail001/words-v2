import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import MissingGreenlet

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.main import app
from app.services.knowledge_map import normalize_confusable_words
from app.models.user import User
from app.models.word import Word
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.word_relation import WordRelation
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun


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



def make_meaning_example(meaning_id: uuid.UUID, sentence: str = "I go to the bank.") -> MeaningExample:
    return MeaningExample(
        id=uuid.uuid4(),
        meaning_id=meaning_id,
        sentence=sentence,
        order_index=0,
        source="lexicon_snapshot",
        confidence=0.9,
    )


def make_word_relation(word_id: uuid.UUID, meaning_id: uuid.UUID, relation_type: str = "synonym", related_word: str = "shore") -> WordRelation:
    return WordRelation(
        id=uuid.uuid4(),
        word_id=word_id,
        meaning_id=meaning_id,
        relation_type=relation_type,
        related_word=related_word,
        source="lexicon_snapshot",
        confidence=0.8,
    )


def make_enrichment_run() -> LexiconEnrichmentRun:
    return LexiconEnrichmentRun(
        id=uuid.uuid4(),
        enrichment_job_id=uuid.uuid4(),
        generator_provider="lexicon_snapshot",
        generator_model="gpt-5.1",
        prompt_version="v1",
        prompt_hash="hash-123",
        verdict="imported",
        confidence=0.9,
        token_input=123,
        token_output=45,
        estimated_cost=0.01,
    )


def test_normalize_confusable_words_falls_back_when_relationship_would_lazy_load():
    class LazyConfusableWord:
        confusable_words = [{"word": "drum", "note": "Instrument, not verb."}]

        @property
        def confusable_entries(self):
            raise MissingGreenlet("lazy load attempted", None, None)

    assert normalize_confusable_words(LazyConfusableWord()) == [
        {"word": "drum", "note": "Instrument, not verb."}
    ]


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


class TestWordEnrichmentDetail:
    @pytest.mark.asyncio
    async def test_get_word_enrichment_by_id(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = make_word("bank")
        meaning = make_meaning(word.id, "A financial institution")
        run = make_enrichment_run()
        word.phonetics = {
            "us": {"ipa": "/bæŋk/", "confidence": 0.99},
            "uk": {"ipa": "/bæŋk/", "confidence": 0.98},
            "au": {"ipa": "/bæŋk/", "confidence": 0.97},
        }
        word.phonetic = "/bæŋk/"
        word.phonetic_source = "lexicon_snapshot"
        word.phonetic_confidence = 0.95
        word.phonetic_enrichment_run_id = run.id
        word.cefr_level = "B1"
        word.learner_part_of_speech = ["noun"]
        word.confusable_words = [{"word": "bench", "note": "Different object."}]
        word.learner_generated_at = run.created_at
        meaning.wn_synset_id = "bank.n.09"
        meaning.primary_domain = "business"
        meaning.secondary_domains = ["stale-domain"]
        meaning.register_label = "neutral"
        meaning.grammar_patterns = ["stale-pattern"]
        meaning.usage_note = "Common everyday noun."
        meaning.learner_generated_at = run.created_at
        meaning.metadata_entries = [
            MagicMock(metadata_kind="secondary_domain", value="finance", order_index=0),
            MagicMock(metadata_kind="grammar_pattern", value="bank + on", order_index=0),
        ]
        example = make_meaning_example(meaning.id, "I deposited cash at the bank.")
        example.difficulty = "A2"
        example.enrichment_run_id = run.id
        relation = make_word_relation(word.id, meaning.id, relation_type="synonym", related_word="lender")
        relation.enrichment_run_id = run.id

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]
        examples_result = MagicMock()
        examples_result.scalars.return_value.all.return_value = [example]
        relations_result = MagicMock()
        relations_result.scalars.return_value.all.return_value = [relation]
        runs_result = MagicMock()
        runs_result.scalars.return_value.all.return_value = [run]
        mock_db.execute.side_effect = [user_result, word_result, meanings_result, examples_result, relations_result, runs_result]

        response = await client.get(
            f"/api/words/{word.id}/enrichment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["word"] == "bank"
        assert data["phonetics"]["us"]["ipa"] == "/bæŋk/"
        assert data["phonetics"]["au"]["confidence"] == 0.97
        assert data["phonetic"] == "/bæŋk/"
        assert data["phonetic_source"] == "lexicon_snapshot"
        assert data["phonetic_confidence"] == 0.95
        assert data["phonetic_enrichment_run_id"] == str(run.id)
        assert data["cefr_level"] == "B1"
        assert data["part_of_speech"] == ["noun"]
        assert data["confusable_words"] == [{"word": "bench", "note": "Different object."}]
        assert data["learner_generated_at"] == run.created_at.isoformat()
        assert len(data["meanings"]) == 1
        assert data["meanings"][0]["definition"] == "A financial institution"
        assert data["meanings"][0]["wn_synset_id"] == "bank.n.09"
        assert data["meanings"][0]["primary_domain"] == "business"
        assert data["meanings"][0]["secondary_domains"] == ["finance"]
        assert data["meanings"][0]["register"] == "neutral"
        assert data["meanings"][0]["grammar_patterns"] == ["bank + on"]
        assert data["meanings"][0]["usage_note"] == "Common everyday noun."
        assert data["meanings"][0]["learner_generated_at"] == run.created_at.isoformat()
        assert len(data["meanings"][0]["examples"]) == 1
        assert data["meanings"][0]["examples"][0]["sentence"] == "I deposited cash at the bank."
        assert data["meanings"][0]["examples"][0]["difficulty"] == "A2"
        assert len(data["meanings"][0]["relations"]) == 1
        assert data["meanings"][0]["relations"][0]["relation_type"] == "synonym"
        assert data["meanings"][0]["relations"][0]["related_word"] == "lender"
        assert len(data["enrichment_runs"]) == 1
        assert data["enrichment_runs"][0]["generator_model"] == "gpt-5.1"
        assert data["enrichment_runs"][0]["verdict"] == "imported"

    @pytest.mark.asyncio
    async def test_get_word_enrichment_prefers_normalized_confusable_rows(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)
        word = make_word("bank")
        meaning = make_meaning(word.id, "A financial institution")
        word.confusable_words = None
        word.confusable_entries = [
            MagicMock(confusable_word="bench", note="Different object.", order_index=0),
            MagicMock(confusable_word="river bank", note=None, order_index=1),
        ]

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]
        examples_result = MagicMock()
        examples_result.scalars.return_value.all.return_value = []
        relations_result = MagicMock()
        relations_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [user_result, word_result, meanings_result, examples_result, relations_result]

        response = await client.get(
            f"/api/words/{word.id}/enrichment",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["confusable_words"] == [
            {"word": "bench", "note": "Different object."},
            {"word": "river bank", "note": None},
        ]

    @pytest.mark.asyncio
    async def test_get_word_enrichment_not_found(self, client, mock_db, auth_token):
        token, user_id = auth_token
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, word_result]

        fake_id = uuid.uuid4()
        response = await client.get(
            f"/api/words/{fake_id}/enrichment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Word not found"

    @pytest.mark.asyncio
    async def test_get_word_enrichment_requires_auth(self, client):
        response = await client.get(f"/api/words/{uuid.uuid4()}/enrichment")
        assert response.status_code == 401
