import unittest
import uuid
from dataclasses import dataclass, field
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


if __name__ == "__main__":
    unittest.main()
