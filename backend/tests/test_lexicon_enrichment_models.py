import uuid

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.meaning_metadata import MeaningMetadata
from app.models.word import Word
from app.models.word_confusable import WordConfusable
from app.models.word_part_of_speech import WordPartOfSpeech
from app.models.word_relation import WordRelation
from app.models.schema_names import LEXICON_SCHEMA


class TestWordEnrichmentFields:
    def test_word_has_phonetic_enrichment_fields(self):
        word = Word(
            word="bank",
            language="en",
            phonetics={
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/bæŋk/", "confidence": 0.98},
                "au": {"ipa": "/bæŋk/", "confidence": 0.97},
            },
            phonetic_source="llm",
            phonetic_confidence=0.9,
            cefr_level="B1",
        )
        word.part_of_speech_entries = [WordPartOfSpeech(word_id=uuid.uuid4(), value="noun", order_index=0)]
        word.confusable_entries = [WordConfusable(word_id=uuid.uuid4(), confusable_word="bench", note="Different object.", order_index=0)]
        assert word.phonetics["us"]["ipa"] == "/bæŋk/"
        assert word.phonetic_source == "llm"
        assert word.phonetic_confidence == 0.9
        assert word.phonetic_enrichment_run_id is None
        assert word.cefr_level == "B1"
        assert [row.value for row in word.part_of_speech_entries] == ["noun"]
        assert [row.confusable_word for row in word.confusable_entries] == ["bench"]
        assert word.learner_generated_at is None
        constraints = [c for c in Word.__table__.constraints if isinstance(c, CheckConstraint)]
        assert any(c.name == "ck_words_phonetic_confidence_range" for c in constraints)


class TestMeaningLearnerFields:
    def test_meaning_accepts_learner_facing_metadata(self):
        meaning = Meaning(
            word_id=uuid.uuid4(),
            definition="A financial institution",
            wn_synset_id="bank.n.09",
            primary_domain="business",
            register_label="neutral",
            usage_note="Common everyday noun.",
        )
        meaning.metadata_entries = [
            MeaningMetadata(meaning_id=meaning.id, metadata_kind="secondary_domain", value="finance", order_index=0),
            MeaningMetadata(meaning_id=meaning.id, metadata_kind="grammar_pattern", value="bank + on", order_index=0),
        ]
        assert meaning.wn_synset_id == "bank.n.09"
        assert meaning.primary_domain == "business"
        assert [row.value for row in meaning.metadata_entries if row.metadata_kind == "secondary_domain"] == ["finance"]
        assert meaning.register_label == "neutral"
        assert [row.value for row in meaning.metadata_entries if row.metadata_kind == "grammar_pattern"] == ["bank + on"]
        assert meaning.usage_note == "Common everyday noun."
        assert meaning.learner_generated_at is None


class TestMeaningExampleModel:
    def test_defaults_and_constraints(self):
        example = MeaningExample(meaning_id=uuid.uuid4(), sentence="I went to the bank.", difficulty="A2")
        assert example.order_index == 0
        assert example.created_at is not None
        assert example.difficulty == "A2"
        unique_constraints = [c for c in MeaningExample.__table__.constraints if isinstance(c, UniqueConstraint)]
        check_constraints = [c for c in MeaningExample.__table__.constraints if isinstance(c, CheckConstraint)]
        assert any(c.name == "uq_meaning_example_meaning_sentence" for c in unique_constraints)
        assert any(c.name == "ck_meaning_examples_confidence_range" for c in check_constraints)


class TestWordRelationModel:
    def test_defaults_and_constraints(self):
        relation = WordRelation(word_id=uuid.uuid4(), relation_type="synonym", related_word="shore")
        assert relation.created_at is not None
        unique_constraints = [c for c in WordRelation.__table__.constraints if isinstance(c, UniqueConstraint)]
        check_constraints = [c for c in WordRelation.__table__.constraints if isinstance(c, CheckConstraint)]
        assert any(c.name == "uq_word_relation_scope" for c in unique_constraints)
        assert any(c.name == "ck_word_relations_confidence_range" for c in check_constraints)


class TestLexiconEnrichmentJobModel:
    def test_defaults_and_unique_constraint(self):
        job = LexiconEnrichmentJob(word_id=uuid.uuid4())
        assert job.phase == "phase1"
        assert job.status == "pending"
        assert job.priority == 100
        constraints = [c for c in LexiconEnrichmentJob.__table__.constraints if isinstance(c, UniqueConstraint)]
        assert any(c.name == "uq_lexicon_enrichment_job_word_phase" for c in constraints)


class TestLexiconEnrichmentRunModel:
    def test_defaults_and_constraints(self):
        run = LexiconEnrichmentRun(enrichment_job_id=uuid.uuid4(), confidence=0.8)
        assert run.confidence == 0.8
        assert run.created_at is not None
        constraints = [c for c in LexiconEnrichmentRun.__table__.constraints if isinstance(c, CheckConstraint)]
        assert any(c.name == "ck_lexicon_enrichment_runs_confidence_range" for c in constraints)

    def test_lexicon_enrichment_tables_use_lexicon_schema(self):
        assert MeaningExample.__table__.schema == LEXICON_SCHEMA
        assert WordRelation.__table__.schema == LEXICON_SCHEMA
        assert LexiconEnrichmentJob.__table__.schema == LEXICON_SCHEMA
        assert LexiconEnrichmentRun.__table__.schema == LEXICON_SCHEMA
