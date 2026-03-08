import unittest
import uuid
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock

from tools.lexicon.import_db import ImportSummary, import_compiled_rows


@dataclass
class FakeWord:
    word: str
    language: str = "en"
    frequency_rank: object = None
    word_forms: object = None
    source_type: object = None
    source_reference: object = None
    phonetic_source: object = None
    phonetic_confidence: object = None
    phonetic_enrichment_run_id: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaning:
    word_id: uuid.UUID
    definition: str
    part_of_speech: object = None
    example_sentence: object = None
    order_index: int = 0
    source: object = None
    source_reference: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaningExample:
    meaning_id: uuid.UUID
    sentence: str
    order_index: int = 0
    source: object = None
    confidence: object = None
    enrichment_run_id: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWordRelation:
    word_id: uuid.UUID
    meaning_id: Optional[uuid.UUID]
    relation_type: str
    related_word: str
    related_word_id: object = None
    source: object = None
    confidence: object = None
    enrichment_run_id: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeLexiconEnrichmentJob:
    word_id: uuid.UUID
    phase: str = "phase1"
    status: str = "pending"
    priority: int = 100
    attempt_count: int = 0
    max_attempts: int = 3
    started_at: object = None
    completed_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeLexiconEnrichmentRun:
    enrichment_job_id: uuid.UUID
    generator_provider: object = None
    generator_model: object = None
    prompt_version: object = None
    prompt_hash: object = None
    verdict: object = None
    confidence: object = None
    created_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class ImportCompiledRowsTests(unittest.TestCase):
    def test_import_creates_word_and_meanings_with_provenance(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb", "noun"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": ["runs"],
                    "verb_forms": {
                        "base": "run",
                        "third_person_singular": "runs",
                        "past": "ran",
                        "past_participle": "run",
                        "gerund": "running",
                    },
                    "comparative": None,
                    "superlative": None,
                    "derivations": ["runner"],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                    },
                    {
                        "sense_id": "sn_lx_run_run_n_01_ef567890",
                        "pos": "noun",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "an act of running",
                        "examples": [{"sentence": "She went for a run.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": [],
                        "collocations": ["go for a run"],
                        "grammar_patterns": ["go for a run"],
                        "usage_note": "Common exercise noun.",
                    },
                ],
                "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
        )

        self.assertEqual(summary, ImportSummary(created_words=1, updated_words=0, created_meanings=2, updated_meanings=0))
        self.assertEqual(len(added), 3)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        imported_meanings = [item for item in added if isinstance(item, FakeMeaning)]
        self.assertEqual(imported_word.word, "run")
        self.assertEqual(imported_word.source_type, "lexicon_snapshot")
        self.assertEqual(imported_word.source_reference, "snapshot-20260307")
        self.assertEqual(imported_word.word_forms["verb_forms"]["past"], "ran")
        self.assertEqual(imported_meanings[0].source, "lexicon_snapshot")
        self.assertEqual(imported_meanings[0].source_reference, "snapshot-20260307:sn_lx_run_run_v_01_abcd1234")
        self.assertEqual(imported_meanings[1].order_index, 1)

    def test_import_updates_existing_word_and_meanings_without_duplication(self) -> None:
        existing_word = FakeWord(
            word="run",
            language="en",
            frequency_rank=50,
            source_type="older_source",
            source_reference="old-snapshot",
        )
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="old definition",
            part_of_speech="verb",
            example_sentence="Old example.",
            order_index=0,
            source="older_source",
            source_reference="old-snapshot:old-sense",
        )

        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
        ]
        added = []
        deleted = []
        session.add.side_effect = added.append
        session.delete.side_effect = deleted.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": ["runs"],
                    "verb_forms": {
                        "base": "run",
                        "third_person_singular": "runs",
                        "past": "ran",
                        "past_participle": "run",
                        "gerund": "running",
                    },
                    "comparative": None,
                    "superlative": None,
                    "derivations": ["runner"],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
        )

        self.assertEqual(summary, ImportSummary(created_words=0, updated_words=1, created_meanings=0, updated_meanings=1))
        self.assertEqual(existing_word.frequency_rank, 5)
        self.assertEqual(existing_word.source_reference, "snapshot-20260307")
        self.assertEqual(existing_meaning.definition, "to move quickly on foot")
        self.assertEqual(existing_meaning.example_sentence, "I run every morning.")
        self.assertEqual(existing_meaning.source_reference, "snapshot-20260307:sn_lx_run_run_v_01_abcd1234")
        self.assertEqual(added, [])
        self.assertEqual(deleted, [])

    def test_import_creates_examples_relations_and_enrichment_provenance_when_models_are_provided(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
            _ScalarResult(None),
            _ListResult([]),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [
                            {"sentence": "I run every morning.", "difficulty": "A1"},
                            {"sentence": "They run together on Sundays.", "difficulty": "A2"},
                        ],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_run_v_01_abcd1234_v1",
                        "generation_run_id": "run-123",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.91,
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_words, 1)
        self.assertEqual(summary.created_meanings, 1)
        self.assertEqual(summary.created_examples, 2)
        self.assertEqual(summary.created_relations, 3)
        self.assertEqual(summary.created_enrichment_jobs, 1)
        self.assertEqual(summary.created_enrichment_runs, 1)

        imported_job = next(item for item in added if isinstance(item, FakeLexiconEnrichmentJob))
        imported_run = next(item for item in added if isinstance(item, FakeLexiconEnrichmentRun))
        imported_examples = [item for item in added if isinstance(item, FakeMeaningExample)]
        imported_relations = [item for item in added if isinstance(item, FakeWordRelation)]

        self.assertEqual(imported_job.phase, "phase1")
        self.assertEqual(imported_job.status, "completed")
        self.assertEqual(imported_run.generator_model, "gpt-5.1")
        self.assertEqual(imported_run.prompt_version, "v1")
        self.assertEqual(imported_run.confidence, 0.91)
        self.assertEqual([item.sentence for item in imported_examples], [
            "I run every morning.",
            "They run together on Sundays.",
        ])
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in imported_relations],
            [("synonym", "jog"), ("antonym", "walk"), ("collocation", "run fast")],
        )
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_examples))
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_relations))


    def test_import_reuses_job_and_run_and_replaces_examples_and_relations(self) -> None:
        existing_word = FakeWord(word="run", language="en", frequency_rank=50)
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="old definition",
            part_of_speech="verb",
            example_sentence="Old example.",
            order_index=0,
            source="lexicon_snapshot",
            source_reference="snapshot-20260307:sn_lx_run_run_v_01_abcd1234",
        )
        existing_job = FakeLexiconEnrichmentJob(word_id=existing_word.id, status="completed")
        existing_run = FakeLexiconEnrichmentRun(
            enrichment_job_id=existing_job.id,
            generator_provider="lexicon_snapshot",
            generator_model="gpt-5.1",
            prompt_version="v1",
            prompt_hash="ignored-in-fake-tests",
            verdict="imported",
            confidence=0.5,
        )
        old_example = FakeMeaningExample(
            meaning_id=existing_meaning.id,
            sentence="Old example.",
            order_index=0,
            source="lexicon_snapshot",
            confidence=0.5,
            enrichment_run_id=existing_run.id,
        )
        old_relation = FakeWordRelation(
            word_id=existing_word.id,
            meaning_id=existing_meaning.id,
            relation_type="synonym",
            related_word="sprint",
            source="lexicon_snapshot",
            confidence=0.5,
            enrichment_run_id=existing_run.id,
        )

        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
            _ScalarResult(existing_job),
            _ScalarResult(existing_run),
            _ListResult([old_example]),
            _ListResult([old_relation]),
        ]
        added = []
        deleted = []
        session.add.side_effect = added.append
        session.delete.side_effect = deleted.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": [],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_run_v_01_abcd1234_v1",
                        "generation_run_id": "run-123",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.91,
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.updated_words, 1)
        self.assertEqual(summary.updated_meanings, 1)
        self.assertEqual(summary.reused_enrichment_jobs, 1)
        self.assertEqual(summary.reused_enrichment_runs, 1)
        self.assertEqual(summary.deleted_examples, 1)
        self.assertEqual(summary.deleted_relations, 1)
        self.assertEqual(summary.created_examples, 1)
        self.assertEqual(summary.created_relations, 2)
        self.assertEqual(deleted, [old_example, old_relation])
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in added if isinstance(item, FakeWordRelation)],
            [("synonym", "jog"), ("antonym", "walk")],
        )


if __name__ == "__main__":
    unittest.main()
