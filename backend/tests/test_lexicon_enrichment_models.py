import uuid

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
from app.models.meaning_example import MeaningExample
from app.models.word import Word
from app.models.word_relation import WordRelation


class TestWordEnrichmentFields:
    def test_word_has_phonetic_enrichment_fields(self):
        word = Word(word="bank", language="en", phonetic_source="llm", phonetic_confidence=0.9)
        assert word.phonetic_source == "llm"
        assert word.phonetic_confidence == 0.9
        assert word.phonetic_enrichment_run_id is None
        constraints = [c for c in Word.__table__.constraints if isinstance(c, CheckConstraint)]
        assert any(c.name == "ck_words_phonetic_confidence_range" for c in constraints)


class TestMeaningExampleModel:
    def test_defaults_and_constraints(self):
        example = MeaningExample(meaning_id=uuid.uuid4(), sentence="I went to the bank.")
        assert example.order_index == 0
        assert example.created_at is not None
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
