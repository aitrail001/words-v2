import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.security import create_access_token
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.meaning_metadata import MeaningMetadata
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.translation import Translation
from app.models.user import User
from app.models.word import Word
from app.models.word_confusable import WordConfusable
from app.models.word_form import WordForm
from app.models.word_part_of_speech import WordPartOfSpeech
from app.models.word_relation import WordRelation


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

        word_page_result = MagicMock()
        word_page_result.mappings.return_value.all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "display_text": "bank",
                "normalized_form": "bank",
                "language": "en",
                "source_reference": "snapshot-001",
                "cefr_level": "B1",
                "frequency_rank": 100,
                "secondary_label": "bæŋk",
                "created_at": datetime.now(timezone.utc),
            }
        ]
        phrase_page_result = MagicMock()
        phrase_page_result.mappings.return_value.all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "display_text": "break a leg",
                "normalized_form": "break a leg",
                "language": "en",
                "source_reference": "snapshot-001",
                "cefr_level": "B2",
                "frequency_rank": None,
                "secondary_label": "idiom",
                "created_at": datetime.now(timezone.utc),
            }
        ]
        reference_page_result = MagicMock()
        reference_page_result.mappings.return_value.all.return_value = [
            {
                "id": str(uuid.uuid4()),
                "display_text": "London",
                "normalized_form": "london",
                "language": "en",
                "source_reference": "snapshot-001",
                "cefr_level": None,
                "frequency_rank": None,
                "secondary_label": "name",
                "created_at": datetime.now(timezone.utc),
            },
        ]
        word_count_result = MagicMock()
        word_count_result.scalar_one.return_value = 1
        phrase_count_result = MagicMock()
        phrase_count_result.scalar_one.return_value = 1
        reference_count_result = MagicMock()
        reference_count_result.scalar_one.return_value = 1
        mock_db.execute.side_effect = [
            user_result,
            word_count_result,
            word_page_result,
            phrase_count_result,
            phrase_page_result,
            reference_count_result,
            reference_page_result,
        ]

        response = await client.get(
          "/api/lexicon-inspector/entries?family=all&sort=alpha_asc&limit=25&offset=0",
          headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert int(response.headers["X-Lexicon-Inspector-Query-Count"]) >= 3
        assert float(response.headers["X-Lexicon-Inspector-Query-Time-Ms"]) >= 0.0
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
          source_type="lexicon_snapshot",
          source_reference="snapshot-001",
          confidence_score=0.91,
          generated_at=datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc),
          seed_metadata={"raw_reviewed_as": "idiom"},
          compiled_payload={
              "entry_id": "ph_break_a_leg",
              "entry_type": "phrase",
              "phrase_kind": "idiom",
              "display_form": "break a leg",
              "senses": [
                  {
                      "sense_id": "phrase-1",
                      "definition": "good luck",
                      "part_of_speech": "phrase",
                      "grammar_patterns": ["say + phrase"],
                      "usage_note": "Used before a performance.",
                      "examples": [{"sentence": "Break a leg tonight.", "difficulty": "A1"}],
                      "translations": {
                          "es": {
                              "definition": "buena suerte",
                              "usage_note": "antes de actuar",
                              "examples": ["Buena suerte esta noche."],
                          }
                      },
                  }
              ],
          },
          created_at=datetime.now(timezone.utc),
        )
        phrase_result = MagicMock()
        phrase_result.scalar_one_or_none.return_value = phrase
        phrase_sense = PhraseSense(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            definition="good luck",
            part_of_speech="phrase",
            order_index=0,
        )
        phrase_example = PhraseSenseExample(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            sentence="Break a leg tonight.",
            order_index=0,
        )
        storage_policy = LexiconVoiceStoragePolicy(
            id=uuid.uuid4(),
            policy_key="word_default",
            source_reference="global",
            content_scope="word",
            provider="default",
            family="default",
            locale="all",
            primary_storage_kind="local",
            primary_storage_base="/tmp/voice",
            fallback_storage_kind=None,
            fallback_storage_base=None,
        )
        phrase_voice_asset = LexiconVoiceAsset(
            id=uuid.uuid4(),
            phrase_entry_id=phrase.id,
            storage_policy_id=storage_policy.id,
            storage_policy=storage_policy,
            content_scope="word",
            locale="en-GB",
            voice_role="female",
            provider="google",
            family="neural2",
            voice_id="en-GB-Neural2-F",
            profile_key="word",
            audio_format="mp3",
            mime_type="audio/mpeg",
            relative_path="phrase_break_a_leg/word/en_gb/female-word-123.mp3",
            source_text="break a leg",
            source_text_hash="voice-hash",
            status="generated",
        )
        phrase_definition_asset = LexiconVoiceAsset(
            id=uuid.uuid4(),
            phrase_sense_id=phrase_sense.id,
            storage_policy_id=storage_policy.id,
            storage_policy=storage_policy,
            content_scope="definition",
            locale="en-GB",
            voice_role="male",
            provider="google",
            family="neural2",
            voice_id="en-GB-Neural2-B",
            profile_key="definition",
            audio_format="mp3",
            mime_type="audio/mpeg",
            relative_path="phrase_break_a_leg/definition/en_gb/male-definition-123.mp3",
            source_text="good luck",
            source_text_hash="voice-hash-2",
            status="generated",
        )
        phrase_example_asset = LexiconVoiceAsset(
            id=uuid.uuid4(),
            phrase_sense_example_id=phrase_example.id,
            storage_policy_id=storage_policy.id,
            storage_policy=storage_policy,
            content_scope="example",
            locale="en-US",
            voice_role="female",
            provider="google",
            family="neural2",
            voice_id="en-US-Neural2-C",
            profile_key="example",
            audio_format="mp3",
            mime_type="audio/mpeg",
            relative_path="phrase_break_a_leg/example/en_us/female-example-123.mp3",
            source_text="Break a leg tonight.",
            source_text_hash="voice-hash-3",
            status="generated",
        )
        phrase_senses_result = MagicMock()
        phrase_senses_result.scalars.return_value.all.return_value = [phrase_sense.id]
        phrase_examples_result = MagicMock()
        phrase_examples_result.scalars.return_value.all.return_value = [phrase_example.id]
        voice_assets_result = MagicMock()
        voice_assets_result.scalars.return_value.all.return_value = [
            phrase_definition_asset,
            phrase_example_asset,
            phrase_voice_asset,
        ]
        mock_db.execute.side_effect = [
            user_result,
            phrase_result,
            phrase_senses_result,
            phrase_examples_result,
            voice_assets_result,
        ]

        response = await client.get(
          f"/api/lexicon-inspector/entries/phrase/{phrase.id}",
          headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["family"] == "phrase"
        assert data["phrase_kind"] == "idiom"
        assert data["source_type"] == "lexicon_snapshot"
        assert data["confidence_score"] == 0.91
        assert data["seed_metadata"] == {"raw_reviewed_as": "idiom"}
        assert data["generated_at"] == "2026-03-20T00:00:00+00:00"
        assert data["senses"][0]["definition"] == "good luck"
        assert data["senses"][0]["examples"][0]["sentence"] == "Break a leg tonight."
        assert data["senses"][0]["translations"][0]["locale"] == "es"
        assert data["senses"][0]["translations"][0]["definition"] == "buena suerte"
        assert len(data["voice_assets"]) == 3
        assert data["voice_assets"][0]["playback_url"].startswith("/api/words/voice-assets/")
        assert data["voice_assets"][0]["relative_path"] == "phrase_break_a_leg/definition/en_gb/male-definition-123.mp3"
        assert data["voice_assets"][0]["resolved_target_url"] is None
        assert data["voice_paths"]["word"]["resolved_target_base"] == "/tmp/voice"
        assert data["voice_paths"]["definition"]["resolved_target_base"] == "/tmp/voice"
        assert data["voice_paths"]["example"]["resolved_target_base"] == "/tmp/voice"

    @pytest.mark.asyncio
    async def test_word_detail_returns_rich_top_level_and_meaning_payload(self, client, mock_db):
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
            phonetics={"us": {"ipa": "/bæŋk/"}, "uk": {"ipa": "/bæŋk/"}},
            phonetic_source="lexicon_snapshot",
            phonetic_confidence=0.98,
            cefr_level="B1",
            frequency_rank=100,
            source_type="lexicon_snapshot",
            source_reference="snapshot-001",
            learner_generated_at=datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        word.part_of_speech_entries = [
            WordPartOfSpeech(word_id=word.id, value="noun", order_index=0),
            WordPartOfSpeech(word_id=word.id, value="verb", order_index=1),
        ]
        word.confusable_entries = [
            WordConfusable(word_id=word.id, confusable_word="bench", note="form", order_index=0),
        ]
        word.form_entries = [
            WordForm(word_id=word.id, form_kind="plural", form_slot="", value="banks", order_index=0),
        ]
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = word

        meaning = Meaning(
            id=uuid.uuid4(),
            word_id=word.id,
            definition="a financial institution",
            part_of_speech="noun",
            primary_domain="money",
            register_label="neutral",
            usage_note="Common everyday sense.",
            example_sentence="She went to the bank.",
            source="compiled",
            source_reference="snapshot-001",
            learner_generated_at=datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc),
            order_index=0,
            created_at=datetime.now(timezone.utc),
        )
        meaning.metadata_entries = [
            MeaningMetadata(meaning_id=meaning.id, metadata_kind="secondary_domain", value="finance", order_index=0),
            MeaningMetadata(meaning_id=meaning.id, metadata_kind="grammar_pattern", value="countable noun", order_index=0),
        ]
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [meaning]

        run = LexiconEnrichmentRun(
            id=uuid.uuid4(),
            generator_model="gpt-5-nano",
            validator_model="gpt-5-nano",
            prompt_version="word_only.v1",
            verdict="accepted",
            created_at=datetime.now(timezone.utc),
        )
        runs_result = MagicMock()
        runs_result.scalars.return_value.all.return_value = [run]

        example = MeaningExample(
            id=uuid.uuid4(),
            meaning_id=meaning.id,
            sentence="She went to the bank.",
            difficulty="A1",
            enrichment_run_id=run.id,
            order_index=0,
        )
        examples_result = MagicMock()
        examples_result.scalars.return_value.all.return_value = [example]

        relation = WordRelation(
            id=uuid.uuid4(),
            word_id=word.id,
            meaning_id=meaning.id,
            relation_type="confusable",
            related_word="bench",
        )
        relations_result = MagicMock()
        relations_result.scalars.return_value.all.return_value = [relation]

        translation = Translation(
            id=uuid.uuid4(),
            meaning_id=meaning.id,
            language="es",
            translation="banco",
        )
        translations_result = MagicMock()
        translations_result.scalars.return_value.all.return_value = [translation]
        storage_policy = LexiconVoiceStoragePolicy(
            id=uuid.uuid4(),
            policy_key="word_default",
            source_reference="global",
            content_scope="word",
            provider="default",
            family="default",
            locale="all",
            primary_storage_kind="local",
            primary_storage_base="/tmp/voice",
            fallback_storage_kind=None,
            fallback_storage_base=None,
        )
        voice_asset = LexiconVoiceAsset(
            id=uuid.uuid4(),
            word_id=word.id,
            storage_policy_id=storage_policy.id,
            storage_policy=storage_policy,
            content_scope="word",
            locale="en-US",
            voice_role="female",
            provider="google",
            family="neural2",
            voice_id="en-US-Neural2-C",
            profile_key="word",
            audio_format="mp3",
            mime_type="audio/mpeg",
            relative_path="word_bank/word/en_us/female-word-123.mp3",
            source_text="bank",
            source_text_hash="hash",
            status="generated",
            created_at=datetime.now(timezone.utc),
        )
        voice_assets_result = MagicMock()
        voice_assets_result.scalars.return_value.all.return_value = [voice_asset]

        mock_db.execute.side_effect = [
            user_result,
            word_result,
            meanings_result,
            examples_result,
            translations_result,
            relations_result,
            runs_result,
            voice_assets_result,
        ]

        response = await client.get(
            f"/api/lexicon-inspector/entries/word/{word.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["family"] == "word"
        assert data["phonetics"]["us"]["ipa"] == "/bæŋk/"
        assert data["learner_part_of_speech"] == ["noun", "verb"]
        assert data["confusable_words"][0]["word"] == "bench"
        assert data["word_forms"]["plural_forms"] == ["banks"]
        assert data["source_type"] == "lexicon_snapshot"
        assert data["learner_generated_at"] == "2026-03-21T00:00:00+00:00"
        assert len(data["meanings"]) == 1
        assert data["meanings"][0]["primary_domain"] == "money"
        assert data["meanings"][0]["secondary_domains"] == ["finance"]
        assert data["meanings"][0]["grammar_patterns"] == ["countable noun"]
        assert data["meanings"][0]["usage_note"] == "Common everyday sense."
        assert data["meanings"][0]["translations"] == [{"id": str(translation.id), "language": "es", "translation": "banco"}]
        assert len(data["enrichment_runs"]) == 1
        assert len(data["voice_assets"]) == 1
        assert data["voice_assets"][0]["playback_url"].startswith("/api/words/voice-assets/")
        assert data["voice_assets"][0]["playback_route_kind"] == "backend_content_route"
        assert data["voice_assets"][0]["primary_target_kind"] == "local"
        assert data["voice_assets"][0]["relative_path"] == "word_bank/word/en_us/female-word-123.mp3"
        assert data["voice_assets"][0]["resolved_target_url"] is None
        assert data["voice_paths"]["word"]["resolved_target_base"] == "/tmp/voice"

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
