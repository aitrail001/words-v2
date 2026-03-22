import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.security import create_access_token
from app.models.phrase_entry import PhraseEntry
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.user import User
from app.models.word import Word


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="inspector@example.com", password_hash="hashed", role=role)


class TestLexiconInspectorApi:
    @pytest.mark.asyncio
    async def test_browse_entries_returns_mixed_families(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user

        word = Word(
          id=uuid.uuid4(),
          word="bank",
          language="en",
          phonetic="bæŋk",
          cefr_level="B1",
          frequency_rank=100,
          source_reference="snapshot-001",
          created_at=datetime.now(timezone.utc),
        )
        phrase = PhraseEntry(
          id=uuid.uuid4(),
          phrase_text="break a leg",
          normalized_form="break a leg",
          phrase_kind="idiom",
          language="en",
          cefr_level="B2",
          source_reference="snapshot-001",
          created_at=datetime.now(timezone.utc),
        )
        reference = ReferenceEntry(
          id=uuid.uuid4(),
          reference_type="name",
          display_form="London",
          normalized_form="london",
          translation_mode="borrowed",
          brief_description="city",
          pronunciation="ˈlʌndən",
          language="en",
          source_reference="snapshot-001",
          created_at=datetime.now(timezone.utc),
        )

        word_result = MagicMock()
        word_result.scalars.return_value.all.return_value = [word]
        phrase_result = MagicMock()
        phrase_result.scalars.return_value.all.return_value = [phrase]
        reference_result = MagicMock()
        reference_result.scalars.return_value.all.return_value = [reference]
        mock_db.execute.side_effect = [user_result, word_result, phrase_result, reference_result]

        response = await client.get(
          "/api/lexicon-inspector/entries?family=all&sort=alpha_asc&limit=25&offset=0",
          headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert {item["family"] for item in data["items"]} == {"word", "phrase", "reference"}

    @pytest.mark.asyncio
    async def test_phrase_detail_returns_phrase_payload(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        phrase = PhraseEntry(
          id=uuid.uuid4(),
          phrase_text="break a leg",
          normalized_form="break a leg",
          phrase_kind="idiom",
          language="en",
          cefr_level="B2",
          register_label="informal",
          brief_usage_note="used before performances",
          source_reference="snapshot-001",
          created_at=datetime.now(timezone.utc),
        )
        phrase_result = MagicMock()
        phrase_result.scalar_one_or_none.return_value = phrase
        mock_db.execute.side_effect = [user_result, phrase_result]

        response = await client.get(
          f"/api/lexicon-inspector/entries/phrase/{phrase.id}",
          headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["family"] == "phrase"
        assert data["phrase_kind"] == "idiom"

    @pytest.mark.asyncio
    async def test_reference_detail_returns_localizations(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        entry = ReferenceEntry(
          id=uuid.uuid4(),
          reference_type="name",
          display_form="London",
          normalized_form="london",
          translation_mode="borrowed",
          brief_description="city",
          pronunciation="ˈlʌndən",
          language="en",
          source_reference="snapshot-001",
          created_at=datetime.now(timezone.utc),
        )
        entry_result = MagicMock()
        entry_result.scalar_one_or_none.return_value = entry
        localization = ReferenceLocalization(
          id=uuid.uuid4(),
          reference_entry_id=entry.id,
          locale="ja",
          display_form="ロンドン",
          brief_description="都市",
          translation_mode="borrowed",
          created_at=datetime.now(timezone.utc),
        )
        localizations_result = MagicMock()
        localizations_result.scalars.return_value.all.return_value = [localization]
        mock_db.execute.side_effect = [user_result, entry_result, localizations_result]

        response = await client.get(
          f"/api/lexicon-inspector/entries/reference/{entry.id}",
          headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["family"] == "reference"
        assert len(data["localizations"]) == 1
