from __future__ import annotations

import unittest

from tools.lexicon.contracts import REQUIRED_TRANSLATION_LOCALES
from tools.lexicon.schemas.word_enrichment_schema import normalize_word_enrichment_payload


class NormalizationPreservesExistingContractTests(unittest.TestCase):
    def test_word_payload_normalization_preserves_existing_fields(self) -> None:
        payload = {
            "definition": "  move quickly on foot  ",
            "examples": [
                {"sentence": "  I run every morning.  ", "difficulty": "A1"},
            ],
            "cefr_level": " B1 ",
            "primary_domain": " general ",
            "secondary_domains": [" transport ", " "],
            "register": " neutral ",
            "synonyms": [" jog ", ""],
            "antonyms": [" walk "],
            "collocations": [" run fast "],
            "grammar_patterns": [" run + adverb "],
            "usage_note": "  Common everyday verb.  ",
            "forms": {
                "plural_forms": [" runs ", ""],
                "verb_forms": {
                    "base": " run ",
                    "third_person_singular": " runs ",
                    "past": " ran ",
                    "past_participle": " run ",
                    "gerund": " running ",
                },
                "comparative": None,
                "superlative": None,
                "derivations": [" runner "],
            },
            "confusable_words": [{"word": " ran ", "note": " Past tense form. "}],
            "confidence": 0.9,
            "translations": {
                locale: {
                    "definition": f"{locale} definition",
                    "usage_note": f"{locale} usage note",
                    "examples": [f"{locale} example"],
                }
                for locale in REQUIRED_TRANSLATION_LOCALES
            },
        }

        normalized = normalize_word_enrichment_payload(payload)

        self.assertEqual(normalized["definition"], "move quickly on foot")
        self.assertEqual(normalized["examples"][0].sentence, "I run every morning.")
        self.assertEqual(normalized["examples"][0].difficulty, "A1")
        self.assertEqual(normalized["cefr_level"], "B1")
        self.assertEqual(normalized["primary_domain"], " general ")
        self.assertEqual(normalized["secondary_domains"], ["transport"])
        self.assertEqual(normalized["register"], "neutral")
        self.assertEqual(normalized["synonyms"], ["jog"])
        self.assertEqual(normalized["antonyms"], ["walk"])
        self.assertEqual(normalized["collocations"], ["run fast"])
        self.assertEqual(normalized["grammar_patterns"], ["run + adverb"])
        self.assertEqual(normalized["usage_note"], "  Common everyday verb.  ")
        self.assertEqual(normalized["forms"]["plural_forms"], ["runs"])
        self.assertEqual(normalized["forms"]["verb_forms"]["base"], "run")
        self.assertEqual(normalized["forms"]["derivations"], ["runner"])
        self.assertEqual(normalized["confusable_words"], [{"word": "ran", "note": "Past tense form."}])
        self.assertEqual(normalized["confidence"], 0.9)
        self.assertEqual(set(normalized["translations"].keys()), set(REQUIRED_TRANSLATION_LOCALES))

    def test_word_payload_normalization_rejects_control_characters(self) -> None:
        payload = {
            "definition": "move quickly on foot",
            "examples": [
                {"sentence": "I run every morning.", "difficulty": "A1"},
            ],
            "cefr_level": "B1",
            "primary_domain": "general",
            "secondary_domains": ["transport"],
            "register": "neutral",
            "synonyms": ["jog"],
            "antonyms": ["walk"],
            "collocations": ["run fast"],
            "grammar_patterns": ["run + adverb"],
            "usage_note": "Common everyday verb.",
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
            "confusable_words": [{"word": "ran", "note": "Past tense form."}],
            "confidence": 0.9,
            "translations": {
                locale: {
                    "definition": f"{locale} definition",
                    "usage_note": f"{locale} usage note",
                    "examples": [f"{locale} example"],
                }
                for locale in REQUIRED_TRANSLATION_LOCALES
            },
        }
        payload["translations"]["es"]["definition"] = "da\x00nar o impedir"

        with self.assertRaisesRegex(RuntimeError, "control character"):
            normalize_word_enrichment_payload(payload)
