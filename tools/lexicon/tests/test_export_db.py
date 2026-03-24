from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import unittest
import uuid

from tools.lexicon.export_db import serialize_phrase_row, serialize_word_row


@dataclass
class FakeTranslation:
    language: str
    translation: str
    usage_note: str | None = None
    examples: list[str] | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaning:
    definition: str
    part_of_speech: str | None = None
    source_reference: str | None = None
    wn_synset_id: str | None = None
    primary_domain: str | None = None
    secondary_domains: list[str] | None = None
    register_label: str | None = None
    grammar_patterns: list[str] | None = None
    usage_note: str | None = None
    learner_generated_at: datetime | None = None
    order_index: int = 0
    translations: list[FakeTranslation] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeExample:
    sentence: str
    difficulty: str | None = None
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeRelation:
    relation_type: str
    related_word: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWord:
    word: str
    language: str = "en"
    source_type: str | None = None
    source_reference: str | None = None
    cefr_level: str | None = None
    frequency_rank: int | None = None
    learner_part_of_speech: list[str] | None = None
    word_forms: dict[str, Any] | None = None
    confusable_words: list[dict[str, Any]] | None = None
    phonetics: dict[str, Any] | None = None
    phonetic: str | None = None
    phonetic_confidence: float | None = None
    learner_generated_at: datetime | None = None
    meanings: list[FakeMeaning] = field(default_factory=list)


@dataclass
class FakePhrase:
    phrase_text: str
    normalized_form: str
    language: str = "en"
    phrase_kind: str = "multiword_expression"
    cefr_level: str | None = None
    register_label: str | None = None
    brief_usage_note: str | None = None
    confidence_score: float | None = None
    generated_at: datetime | None = None
    source_type: str | None = None
    source_reference: str | None = None
    seed_metadata: dict[str, Any] | None = None
    compiled_payload: dict[str, Any] | None = None


class ExportDbTests(unittest.TestCase):
    def test_serialize_word_row_preserves_provenance_and_sense_details(self) -> None:
        meaning = FakeMeaning(
            definition="to move quickly on foot",
            part_of_speech="verb",
            source_reference="fixture-run:sense-001",
            primary_domain="general",
            secondary_domains=["movement"],
            register_label="neutral",
            grammar_patterns=["run + adverb"],
            usage_note="Common learner verb.",
            learner_generated_at=datetime(2026, 3, 24, tzinfo=timezone.utc),
            translations=[
                FakeTranslation(
                    language="es",
                    translation="correr",
                    usage_note="Verbo común de aprendizaje.",
                    examples=["Corro cada mañana."],
                )
            ],
        )
        word = FakeWord(
            word="run",
            source_type="db_export",
            source_reference="fixture-run",
            cefr_level="A1",
            frequency_rank=5,
            learner_part_of_speech=["verb"],
            word_forms={"verb_forms": {"past": "ran"}},
            confusable_words=[{"word": "ran", "note": "Past tense form."}],
            phonetics={"us": {"ipa": "/rʌn/", "confidence": 0.99}},
            phonetic="/rʌn/",
            phonetic_confidence=0.99,
            learner_generated_at=datetime(2026, 3, 24, tzinfo=timezone.utc),
            meanings=[meaning],
        )

        row = serialize_word_row(
            word,
            examples_by_meaning_id={meaning.id: [FakeExample(sentence="I run every morning.", difficulty="A1")]},
            relations_by_meaning_id={meaning.id: [FakeRelation(relation_type="synonym", related_word="jog")]},
        )

        self.assertEqual(row["entry_type"], "word")
        self.assertEqual(row["source_type"], "db_export")
        self.assertEqual(row["source_reference"], "fixture-run")
        self.assertEqual(row["phonetics"]["us"]["ipa"], "/rʌn/")
        self.assertEqual(row["senses"][0]["sense_id"], "sense-001")
        self.assertEqual(row["senses"][0]["translations"]["es"]["definition"], "correr")
        self.assertEqual(row["senses"][0]["translations"]["es"]["usage_note"], "Verbo común de aprendizaje.")
        self.assertEqual(row["senses"][0]["translations"]["es"]["examples"], ["Corro cada mañana."])
        self.assertEqual(row["senses"][0]["synonyms"], ["jog"])
        self.assertEqual(row["senses"][0]["examples"][0]["sentence"], "I run every morning.")

    def test_serialize_phrase_row_prefers_compiled_payload_and_backfills_missing_fields(self) -> None:
        phrase = FakePhrase(
            phrase_text="by and large",
            normalized_form="by and large",
            source_type="db_export",
            source_reference="fixture-phrase",
            compiled_payload={
                "entry_type": "phrase",
                "word": "by and large",
                "normalized_form": "by and large",
                "senses": [{"definition": "in general"}],
            },
        )

        row = serialize_phrase_row(phrase)

        self.assertEqual(row["entry_type"], "phrase")
        self.assertEqual(row["word"], "by and large")
        self.assertEqual(row["source_type"], "db_export")
        self.assertEqual(row["source_reference"], "fixture-phrase")
        self.assertEqual(row["senses"][0]["definition"], "in general")


if __name__ == "__main__":
    unittest.main()
