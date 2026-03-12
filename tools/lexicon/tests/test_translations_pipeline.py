import unittest
import uuid
from dataclasses import dataclass, field
from unittest.mock import MagicMock

from tools.lexicon.compile_export import compile_words
from tools.lexicon.enrich import _validate_openai_compatible_payload
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord
from tools.lexicon.import_db import import_compiled_rows


@dataclass
class FakeWord:
    word: str
    language: str = "en"
    frequency_rank: object = None
    cefr_level: object = None
    learner_part_of_speech: object = None
    confusable_words: object = None
    learner_generated_at: object = None
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
class FakeTranslation:
    meaning_id: uuid.UUID
    language: str
    translation: str
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


class TranslationPayloadValidationTests(unittest.TestCase):
    def test_validate_openai_payload_accepts_required_translation_locales(self) -> None:
        normalized = _validate_openai_compatible_payload(
            {
                "definition": "to move quickly on foot",
                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                "usage_note": "Common everyday verb.",
                "confidence": 0.9,
                "translations": {
                    "zh-Hans": {"definition": "跑步", "usage_note": "常见日常动词。", "examples": ["我每天早上跑步。"]},
                    "es": {"definition": "correr", "usage_note": "Verbo cotidiano común.", "examples": ["Corro todas las mañanas."]},
                    "ar": {"definition": "يركض", "usage_note": "فعل يومي شائع.", "examples": ["أركض كل صباح."]},
                    "pt-BR": {"definition": "correr", "usage_note": "Verbo cotidiano comum.", "examples": ["Eu corro todas as manhãs."]},
                    "ja": {"definition": "走る", "usage_note": "日常でよく使う動詞。", "examples": ["私は毎朝走ります。"]},
                },
            }
        )

        self.assertIn("translations", normalized)
        self.assertEqual(normalized["translations"]["ja"]["definition"], "走る")

    def test_validate_openai_payload_rejects_missing_required_translation_locale(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "field 'translations' must include required locale 'ja'"):
            _validate_openai_compatible_payload(
                {
                    "definition": "to move quickly on foot",
                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                    "usage_note": "Common everyday verb.",
                    "confidence": 0.9,
                    "translations": {
                        "zh-Hans": {"definition": "跑步", "usage_note": "常见日常动词。", "examples": ["我每天早上跑步。"]},
                        "es": {"definition": "correr", "usage_note": "Verbo cotidiano común.", "examples": ["Corro todas las mañanas."]},
                        "ar": {"definition": "يركض", "usage_note": "فعل يومي شائع.", "examples": ["أركض كل صباح."]},
                        "pt-BR": {"definition": "correr", "usage_note": "Verbo cotidiano comum.", "examples": ["Eu corro todas as manhãs."]},
                    },
                }
            )


class CompileWordsTranslationTests(unittest.TestCase):
    def test_compile_words_preserves_sense_translations(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        sense = SenseRecord(
            snapshot_id="snap-1",
            sense_id="sn_lx_run_1",
            lexeme_id="lx_run",
            wn_synset_id="run.v.01",
            part_of_speech="verb",
            canonical_gloss="move fast by using your legs",
            selection_reason="core learner sense",
            sense_order=1,
            is_high_polysemy=False,
            created_at="2026-03-07T00:00:00Z",
        )
        enrichment = EnrichmentRecord(
            snapshot_id="snap-1",
            enrichment_id="en_sn_lx_run_1_v1",
            sense_id="sn_lx_run_1",
            definition="to move quickly on foot",
            examples=[SenseExample(sentence="I run every morning.", difficulty="A1")],
            cefr_level="A1",
            primary_domain="general",
            secondary_domains=[],
            register="neutral",
            synonyms=["jog"],
            antonyms=["walk"],
            collocations=["run fast"],
            grammar_patterns=["run + adverb"],
            usage_note="Common everyday verb.",
            forms={"plural_forms": [], "verb_forms": {"base": "run", "third_person_singular": "runs", "past": "ran", "past_participle": "run", "gerund": "running"}, "comparative": None, "superlative": None, "derivations": []},
            confusable_words=[],
            model_name="gpt-5.1",
            prompt_version="v1",
            generation_run_id="run-123",
            confidence=0.9,
            review_status="approved",
            generated_at="2026-03-07T00:00:00Z",
            translations={
                "zh-Hans": {"definition": "跑步", "usage_note": "常见日常动词。", "examples": ["我每天早上跑步。"]},
                "es": {"definition": "correr", "usage_note": "Verbo cotidiano común.", "examples": ["Corro todas las mañanas."]},
                "ar": {"definition": "يركض", "usage_note": "فعل يومي شائع.", "examples": ["أركض كل صباح."]},
                "pt-BR": {"definition": "correr", "usage_note": "Verbo cotidiano comum.", "examples": ["Eu corro todas as manhãs."]},
                "ja": {"definition": "走る", "usage_note": "日常でよく使う動詞。", "examples": ["私は毎朝走ります。"]},
            },
        )

        compiled = compile_words([lexeme], [sense], [enrichment])

        self.assertEqual(compiled[0].to_dict()["senses"][0]["translations"]["es"]["definition"], "correr")


class ImportCompiledRowsTranslationTests(unittest.TestCase):
    def test_import_compiled_rows_upserts_meaning_translations(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [{
            "schema_version": "1.1.0",
            "word": "run",
            "part_of_speech": ["verb"],
            "cefr_level": "A1",
            "frequency_rank": 5,
            "forms": {"plural_forms": [], "verb_forms": {"base": "run"}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{
                "sense_id": "sn_lx_run_1",
                "pos": "verb",
                "primary_domain": "general",
                "secondary_domains": [],
                "register": "neutral",
                "definition": "to move quickly on foot",
                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                "synonyms": [],
                "antonyms": [],
                "collocations": [],
                "grammar_patterns": [],
                "usage_note": "Common everyday verb.",
                "translations": {
                    "zh-Hans": {"definition": "跑步", "usage_note": "常见日常动词。", "examples": ["我每天早上跑步。"]},
                    "es": {"definition": "correr", "usage_note": "Verbo cotidiano común.", "examples": ["Corro todas las mañanas."]},
                    "ar": {"definition": "يركض", "usage_note": "فعل يومي شائع.", "examples": ["أركض كل صباح."]},
                    "pt-BR": {"definition": "correr", "usage_note": "Verbo cotidiano comum.", "examples": ["Eu corro todas as manhãs."]},
                    "ja": {"definition": "走る", "usage_note": "日常でよく使う動詞。", "examples": ["私は毎朝走ります。"]},
                },
            }],
            "confusable_words": [],
            "generated_at": "2026-03-07T00:00:00Z",
        }]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-1",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            translation_model=FakeTranslation,
            meaning_example_model=None,
            word_relation_model=None,
            lexicon_enrichment_job_model=None,
            lexicon_enrichment_run_model=None,
        )

        translations = [item for item in added if isinstance(item, FakeTranslation)]
        self.assertEqual(summary.created_words, 1)
        self.assertEqual(len(translations), 5)
        self.assertEqual({item.language for item in translations}, {"zh-Hans", "es", "ar", "pt-BR", "ja"})
        self.assertEqual(next(item.translation for item in translations if item.language == "ja"), "走る")


if __name__ == "__main__":
    unittest.main()
