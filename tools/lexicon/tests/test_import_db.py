import json
import tempfile
import unittest
import uuid
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock
from pathlib import Path

from tools.lexicon.import_db import ImportSummary, import_compiled_rows


@dataclass
class FakeWord:
    word: str
    language: str = "en"
    phonetics: object = None
    phonetic: object = None
    frequency_rank: object = None
    cefr_level: object = None
    learner_part_of_speech: object = None
    confusable_words: object = None
    learner_generated_at: object = None
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
    wn_synset_id: object = None
    primary_domain: object = None
    secondary_domains: object = None
    register_label: object = None
    grammar_patterns: object = None
    usage_note: object = None
    learner_generated_at: object = None
    order_index: int = 0
    source: object = None
    source_reference: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaningExample:
    meaning_id: uuid.UUID
    sentence: str
    difficulty: object = None
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


@dataclass
class FakePhraseEntry:
    phrase_text: str
    normalized_form: str
    phrase_kind: str
    language: str = "en"
    cefr_level: object = None
    register_label: object = None
    brief_usage_note: object = None
    compiled_payload: object = None
    seed_metadata: object = None
    confidence_score: object = None
    generated_at: object = None
    source_type: object = None
    source_reference: object = None
    created_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeReferenceEntry:
    reference_type: str
    display_form: str
    normalized_form: str
    translation_mode: str
    brief_description: str
    pronunciation: str
    learner_tip: object = None
    language: str = "en"
    source_type: object = None
    source_reference: object = None
    created_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeReferenceLocalization:
    reference_entry_id: uuid.UUID
    locale: str
    display_form: str
    brief_description: object = None
    translation_mode: object = None
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
            _ScalarResult(None),
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
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
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
        self.assertEqual(imported_word.cefr_level, "A1")
        self.assertEqual(imported_word.learner_part_of_speech, ["verb", "noun"])
        self.assertEqual(imported_word.confusable_words, [{"word": "ran", "note": "Past tense form."}])
        self.assertEqual(imported_word.source_type, "lexicon_snapshot")
        self.assertEqual(imported_word.source_reference, "snapshot-20260307")
        self.assertEqual(imported_word.word_forms["verb_forms"]["past"], "ran")
        self.assertEqual(imported_word.phonetics["au"]["ipa"], "/rɐn/")
        self.assertEqual(imported_word.phonetic, "/rʌn/")
        self.assertEqual(imported_word.phonetic_source, "lexicon_snapshot")
        self.assertEqual(imported_word.phonetic_confidence, 0.99)
        self.assertIsNotNone(imported_word.learner_generated_at)
        self.assertEqual(imported_meanings[0].source, "lexicon_snapshot")
        self.assertEqual(imported_meanings[0].primary_domain, "general")
        self.assertEqual(imported_meanings[0].register_label, "neutral")
        self.assertEqual(imported_meanings[0].grammar_patterns, ["run + adverb"])
        self.assertEqual(imported_meanings[0].usage_note, "Common everyday verb.")
        self.assertEqual(imported_meanings[0].source_reference, "snapshot-20260307:sn_lx_run_run_v_01_abcd1234")
        self.assertEqual(imported_meanings[1].order_index, 1)


    def test_import_applies_word_level_fields_even_without_senses(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "solo",
                "part_of_speech": ["adjective"],
                "cefr_level": "A2",
                "frequency_rank": 1234,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [],
                "confusable_words": [{"word": "single", "note": "Related but not identical."}],
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
        self.assertEqual(summary.created_meanings, 0)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        self.assertEqual(imported_word.cefr_level, "A2")
        self.assertEqual(imported_word.learner_part_of_speech, ["adjective"])
        self.assertEqual(imported_word.confusable_words, [{"word": "single", "note": "Related but not identical."}])
        self.assertIsNotNone(imported_word.learner_generated_at)

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
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
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
        self.assertEqual(existing_word.cefr_level, "A1")
        self.assertEqual(existing_word.learner_part_of_speech, ["verb"])
        self.assertEqual(existing_word.confusable_words, [])
        self.assertIsNotNone(existing_word.learner_generated_at)
        self.assertEqual(existing_word.source_reference, "snapshot-20260307")
        self.assertEqual(existing_meaning.definition, "to move quickly on foot")
        self.assertEqual(existing_meaning.example_sentence, "I run every morning.")
        self.assertEqual(existing_meaning.primary_domain, "general")
        self.assertEqual(existing_meaning.register_label, "neutral")
        self.assertEqual(existing_meaning.grammar_patterns, ["run + adverb"])
        self.assertEqual(existing_meaning.usage_note, "Common everyday verb.")
        self.assertIsNotNone(existing_meaning.learner_generated_at)
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
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
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
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        imported_meaning = next(item for item in added if isinstance(item, FakeMeaning))
        self.assertEqual(imported_word.cefr_level, "A1")
        self.assertEqual(imported_word.learner_part_of_speech, ["verb"])
        self.assertEqual(imported_word.confusable_words, [])
        self.assertIsNotNone(imported_word.learner_generated_at)
        self.assertEqual(imported_meaning.wn_synset_id, "run.v.01")
        self.assertEqual(imported_meaning.primary_domain, "general")
        self.assertEqual(imported_meaning.secondary_domains, [])
        self.assertEqual(imported_meaning.register_label, "neutral")
        self.assertEqual(imported_meaning.grammar_patterns, ["run + adverb"])
        self.assertEqual(imported_meaning.usage_note, "Common everyday verb.")
        self.assertIsNotNone(imported_meaning.learner_generated_at)
        self.assertEqual([item.sentence for item in imported_examples], [
            "I run every morning.",
            "They run together on Sundays.",
        ])
        self.assertEqual([item.difficulty for item in imported_examples], ["A1", "A2"])
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in imported_relations],
            [("synonym", "jog"), ("antonym", "walk"), ("collocation", "run fast")],
        )
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_examples))
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_relations))
        self.assertEqual(imported_word.phonetics["uk"]["ipa"], "/rʌn/")
        self.assertEqual(imported_word.phonetic, "/rʌn/")
        self.assertEqual(imported_word.phonetic_confidence, 0.99)
        self.assertEqual(imported_word.phonetic_enrichment_run_id, imported_run.id)

    def test_import_collapses_same_generation_run_id_to_one_enrichment_run_per_word(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
            _ScalarResult(None),
            _ListResult([]),
            _ListResult([]),
            _ListResult([]),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "set",
                "part_of_speech": ["verb", "noun"],
                "cefr_level": "A1",
                "frequency_rank": 10,
                "forms": {
                    "plural_forms": ["sets"],
                    "verb_forms": {"base": "set", "third_person_singular": "sets", "past": "set", "past_participle": "set", "gerund": "setting"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_set_1",
                        "wn_synset_id": "set.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to put something in a place",
                        "examples": [{"sentence": "She set the cup on the table.", "difficulty": "A1"}],
                        "synonyms": ["place"],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": ["set + object + place"],
                        "usage_note": "Common verb sense.",
                        "enrichment_id": "en_sn_lx_set_1_v1",
                        "generation_run_id": "word-run-1",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.95,
                        "generated_at": "2026-03-12T00:00:00Z",
                    },
                    {
                        "sense_id": "sn_lx_set_2",
                        "wn_synset_id": "set.n.01",
                        "pos": "noun",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "a group of things that belong together",
                        "examples": [{"sentence": "This chess set is old.", "difficulty": "A1"}],
                        "synonyms": ["collection"],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common noun sense.",
                        "enrichment_id": "en_sn_lx_set_2_v1",
                        "generation_run_id": "word-run-1",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.94,
                        "generated_at": "2026-03-12T00:00:00Z",
                    },
                ],
                "confusable_words": [],
                "generated_at": "2026-03-12T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260312",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_enrichment_jobs, 1)
        self.assertEqual(summary.created_enrichment_runs, 1)
        imported_run = next(item for item in added if isinstance(item, FakeLexiconEnrichmentRun))
        imported_examples = [item for item in added if isinstance(item, FakeMeaningExample)]
        imported_relations = [item for item in added if isinstance(item, FakeWordRelation)]
        self.assertEqual(len([item for item in added if isinstance(item, FakeLexiconEnrichmentRun)]), 1)
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_examples))
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_relations))

    def test_import_compiled_rows_supports_phrase_and_reference_rows(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),  # phrase lookup
            _ScalarResult(None),  # reference lookup
            _ListResult([]),      # reference localizations lookup
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [{
                    "sense_id": "phrase-1",
                    "definition": "leave the ground",
                    "part_of_speech": "verb",
                    "examples": [{"sentence": "The plane took off.", "difficulty": "A1"}],
                    "grammar_patterns": ["subject + take off"],
                    "usage_note": "Common for planes.",
                    "translations": {
                        "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。"]},
                        "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó."]},
                        "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة."]},
                        "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou."]},
                        "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。"]},
                    },
                }],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
                "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
                "confidence": 0.91,
            },
            {
                "schema_version": "1.1.0",
                "entry_id": "rf_australia",
                "entry_type": "reference",
                "normalized_form": "australia",
                "source_provenance": [{"source": "reference_seed"}],
                "entity_category": "general",
                "word": "Australia",
                "part_of_speech": [],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "reference_type": "country",
                "display_form": "Australia",
                "translation_mode": "localized",
                "brief_description": "A country in the Southern Hemisphere.",
                "pronunciation": "/ɔˈstreɪliə/",
                "localized_display_form": {"es": "Australia"},
                "localized_brief_description": {"es": "País del hemisferio sur."},
                "learner_tip": "Stress is on STRAY.",
                "localizations": [{"locale": "es", "display_form": "Australia", "translation_mode": "localized"}],
            },
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            reference_model=FakeReferenceEntry,
            reference_localization_model=FakeReferenceLocalization,
        )

        self.assertEqual(summary.created_phrases, 1)
        self.assertEqual(summary.created_reference_entries, 1)
        self.assertEqual(summary.created_reference_localizations, 1)
        self.assertEqual(any(isinstance(item, FakePhraseEntry) for item in added), True)
        self.assertEqual(any(isinstance(item, FakeReferenceEntry) for item in added), True)
        self.assertEqual(any(isinstance(item, FakeReferenceLocalization) for item in added), True)
        imported_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        self.assertEqual(imported_phrase.compiled_payload["entry_id"], "ph_take_off")
        self.assertEqual(imported_phrase.seed_metadata["raw_reviewed_as"], "phrasal verb")
        self.assertEqual(imported_phrase.confidence_score, 0.91)

    def test_load_compiled_rows_reads_family_directory_and_dry_run_counts(self) -> None:
        from tools.lexicon.import_db import load_compiled_rows, summarize_compiled_rows

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "words.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
            }) + "\n", encoding="utf-8")
            (root / "phrases.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
            }) + "\n", encoding="utf-8")
            (root / "references.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "rf_australia",
                "entry_type": "reference",
                "normalized_form": "australia",
                "source_provenance": [{"source": "reference_seed"}],
                "entity_category": "general",
                "word": "Australia",
                "part_of_speech": [],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "reference_type": "country",
                "display_form": "Australia",
                "translation_mode": "localized",
                "brief_description": "A country in the Southern Hemisphere.",
                "pronunciation": "/ɔˈstreɪliə/",
                "localized_display_form": {"es": "Australia"},
                "localized_brief_description": {"es": "País del hemisferio sur."},
                "learner_tip": "Stress is on STRAY.",
                "localizations": [{"locale": "es", "display_form": "Australia", "translation_mode": "localized"}],
            }) + "\n", encoding="utf-8")

            rows = load_compiled_rows(root)
            counts = summarize_compiled_rows(rows)

            self.assertEqual(counts["row_count"], 3)
            self.assertEqual(counts["word_count"], 1)
            self.assertEqual(counts["phrase_count"], 1)
            self.assertEqual(counts["reference_count"], 1)


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
        self.assertEqual(existing_word.cefr_level, "A1")
        self.assertEqual(existing_word.learner_part_of_speech, ["verb"])
        self.assertEqual(existing_meaning.wn_synset_id, "run.v.01")
        self.assertEqual(existing_meaning.primary_domain, "general")
        self.assertEqual(existing_meaning.register_label, "neutral")
        self.assertEqual(existing_meaning.grammar_patterns, ["run + adverb"])
        self.assertEqual(existing_meaning.usage_note, "Common everyday verb.")
        self.assertEqual(deleted, [old_example, old_relation])
        self.assertEqual(session.flush.call_count, 2)
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in added if isinstance(item, FakeWordRelation)],
            [("synonym", "jog"), ("antonym", "walk")],
        )
        self.assertEqual([item.difficulty for item in added if isinstance(item, FakeMeaningExample)], ["A1"])


if __name__ == "__main__":
    unittest.main()
