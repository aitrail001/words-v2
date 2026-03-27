import uuid


import app.models as model_registry
from app.core.database import Base
from app.models.user import User
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.word import Word
from app.models.meaning import Meaning
from app.models.lexicon_job import LexiconJob
from app.models.translation import Translation
from app.models.schema_names import LEXICON_SCHEMA


class TestUserModel:
    def test_user_has_required_fields(self):
        user = User(
            email="test@example.com",
            password_hash="hashed_password",
        )
        assert user.email == "test@example.com"
        assert user.password_hash == "hashed_password"
        assert user.role == "user"
        assert user.tier == "free"
        assert user.is_active is True

    def test_user_role_defaults_to_user(self):
        user = User(email="test@example.com", password_hash="x")
        assert user.role == "user"

    def test_user_tier_defaults_to_free(self):
        user = User(email="test@example.com", password_hash="x")
        assert user.tier == "free"

    def test_user_repr(self):
        user = User(email="test@example.com", password_hash="x")
        assert "test@example.com" in repr(user)


class TestWordModel:
    def test_word_has_required_fields(self):
        word = Word(word="bank")
        assert word.word == "bank"
        assert word.language == "en"

    def test_word_language_defaults_to_en(self):
        word = Word(word="hello")
        assert word.language == "en"

    def test_word_optional_fields_are_nullable(self):
        word = Word(word="test")
        assert word.phonetics is None
        assert word.phonetic is None
        assert word.frequency_rank is None
        assert word.form_entries == []

    def test_word_repr(self):
        word = Word(word="bank")
        assert "bank" in repr(word)

    def test_word_provenance_fields(self):
        word = Word(word="run", source_type="lexicon_snapshot", source_reference="snapshot-20260307")
        assert word.source_type == "lexicon_snapshot"
        assert word.source_reference == "snapshot-20260307"

    def test_word_table_uses_lexicon_schema(self):
        assert Word.__table__.schema == LEXICON_SCHEMA

    def test_word_models_register_confusable_relationship(self):
        assert hasattr(model_registry, "WordConfusable")
        assert "lexicon.word_confusables" in Base.metadata.tables
        assert Word(word="bank").confusable_entries == []

    def test_word_models_register_word_form_relationship(self):
        assert hasattr(model_registry, "WordForm")
        assert "lexicon.word_forms" in Base.metadata.tables
        assert Word(word="bank").form_entries == []

    def test_word_models_register_part_of_speech_relationship(self):
        assert hasattr(model_registry, "WordPartOfSpeech")
        assert "lexicon.word_part_of_speech" in Base.metadata.tables
        assert Word(word="bank").part_of_speech_entries == []

    def test_word_models_register_learner_catalog_projection(self):
        assert hasattr(model_registry, "LearnerCatalogEntry")
        assert "lexicon.learner_catalog_entries" in Base.metadata.tables


class TestPhraseEntryModel:
    def test_phrase_entry_keeps_compiled_payload_and_phrase_senses_relationship(self):
        entry = PhraseEntry(
            phrase_text="take off",
            normalized_form="take off",
            phrase_kind="phrasal_verb",
            compiled_payload={"entry_type": "phrase", "entry_id": "ph_take_off"},
        )
        assert entry.compiled_payload["entry_id"] == "ph_take_off"
        assert entry.phrase_senses == []

    def test_phrase_entry_models_register_through_aggregate_import_path(self):
        assert hasattr(model_registry, "PhraseSense")
        assert hasattr(model_registry, "PhraseSenseLocalization")
        assert hasattr(model_registry, "PhraseSenseExample")
        assert hasattr(model_registry, "PhraseSenseExampleLocalization")
        assert "lexicon.phrase_senses" in Base.metadata.tables
        assert "lexicon.phrase_sense_localizations" in Base.metadata.tables
        assert "lexicon.phrase_sense_examples" in Base.metadata.tables
        assert "lexicon.phrase_sense_example_localizations" in Base.metadata.tables


class TestPhraseSenseModel:
    def test_phrase_sense_exposes_normalized_metadata_fields(self):
        sense = PhraseSense(
            phrase_entry_id=uuid.uuid4(),
            definition="to depart",
            usage_note="Common for planes.",
            part_of_speech="phrasal_verb",
            register="neutral",
            primary_domain="general",
            secondary_domains=["transport"],
            grammar_patterns=["take off + adverb"],
            synonyms=["depart"],
            antonyms=["land"],
            collocations=["take off quickly"],
        )

        assert sense.part_of_speech == "phrasal_verb"
        assert sense.register == "neutral"
        assert sense.primary_domain == "general"
        assert sense.secondary_domains == ["transport"]
        assert sense.grammar_patterns == ["take off + adverb"]
        assert sense.synonyms == ["depart"]
        assert sense.antonyms == ["land"]
        assert sense.collocations == ["take off quickly"]


class TestMeaningModel:
    def test_meaning_has_required_fields(self):
        word_id = uuid.uuid4()
        meaning = Meaning(
            word_id=word_id,
            definition="A financial institution",
        )
        assert meaning.word_id == word_id
        assert meaning.definition == "A financial institution"
        assert meaning.metadata_entries == []
        assert meaning.order_index == 0

    def test_meaning_optional_fields(self):
        meaning = Meaning(
            word_id=uuid.uuid4(),
            definition="test",
        )
        assert meaning.part_of_speech is None
        assert meaning.example_sentence is None

    def test_meaning_repr(self):
        meaning = Meaning(
            word_id=uuid.uuid4(),
            definition="A financial institution",
        )
        assert "A financial institution" in repr(meaning)

    def test_meaning_source_reference_optional(self):
        meaning = Meaning(
            word_id=uuid.uuid4(),
            definition="test",
            source="lexicon_snapshot",
            source_reference="snapshot-20260307:sn_1",
        )
        assert meaning.source == "lexicon_snapshot"
        assert meaning.source_reference == "snapshot-20260307:sn_1"

    def test_meaning_models_register_metadata_relationship(self):
        assert hasattr(model_registry, "MeaningMetadata")
        assert "lexicon.meaning_metadata" in Base.metadata.tables
        meaning = Meaning(word_id=uuid.uuid4(), definition="test")
        assert meaning.metadata_entries == []


class TestTranslationModel:
    def test_translation_has_required_fields(self):
        meaning_id = uuid.uuid4()
        translation = Translation(
            meaning_id=meaning_id,
            language="zh",
            translation="银行",
        )
        assert translation.meaning_id == meaning_id
        assert translation.language == "zh"
        assert translation.translation == "银行"

    def test_meaning_and_translation_tables_use_lexicon_schema(self):
        assert Meaning.__table__.schema == LEXICON_SCHEMA
        assert Translation.__table__.schema == LEXICON_SCHEMA

    def test_translation_models_register_example_relationship(self):
        assert hasattr(model_registry, "TranslationExample")
        assert "lexicon.translation_examples" in Base.metadata.tables
        translation = Translation(meaning_id=uuid.uuid4(), language="es", translation="banco")
        assert translation.example_entries == []


class TestLexiconJobModel:
    def test_lexicon_job_defaults_and_schema(self):
        user_id = uuid.uuid4()
        job = LexiconJob(
            created_by=user_id,
            job_type="import_db",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"},
        )

        assert job.created_by == user_id
        assert job.job_type == "import_db"
        assert job.status == "queued"
        assert job.progress_total == 0
        assert job.progress_completed == 0
        assert job.progress_current_label is None
        assert job.result_payload is None
        assert job.error_message is None
        assert LexiconJob.__table__.schema == LEXICON_SCHEMA


class TestLearnerCatalogEntryModel:
    def test_projection_table_uses_lexicon_schema_and_unique_entry_key(self):
        learner_catalog_entries = Base.metadata.tables["lexicon.learner_catalog_entries"]

        assert learner_catalog_entries.schema == LEXICON_SCHEMA
        assert {"entry_type", "entry_id"} in [
            {column.name for column in constraint.columns}
            for constraint in learner_catalog_entries.constraints
            if getattr(constraint, "columns", None)
        ]
