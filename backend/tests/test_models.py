import uuid


from app.models.user import User
from app.models.word import Word
from app.models.meaning import Meaning
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
        assert word.phonetic is None
        assert word.frequency_rank is None
        assert word.word_forms is None

    def test_word_repr(self):
        word = Word(word="bank")
        assert "bank" in repr(word)

    def test_word_provenance_fields(self):
        word = Word(word="run", source_type="lexicon_snapshot", source_reference="snapshot-20260307")
        assert word.source_type == "lexicon_snapshot"
        assert word.source_reference == "snapshot-20260307"

    def test_word_table_uses_lexicon_schema(self):
        assert Word.__table__.schema == LEXICON_SCHEMA


class TestMeaningModel:
    def test_meaning_has_required_fields(self):
        word_id = uuid.uuid4()
        meaning = Meaning(
            word_id=word_id,
            definition="A financial institution",
        )
        assert meaning.word_id == word_id
        assert meaning.definition == "A financial institution"
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
