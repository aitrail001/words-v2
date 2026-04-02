from __future__ import annotations

import unittest

from tools.lexicon.schemas.phrase_enrichment_schema import (
    build_phrase_enrichment_response_schema,
    normalize_phrase_enrichment_payload,
)


def _translations(example: str) -> dict[str, dict[str, object]]:
    return {
        "zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": [f"zh:{example}"]},
        "es": {"definition": "es:def", "usage_note": "es:note", "examples": [f"es:{example}"]},
        "ar": {"definition": "ar:def", "usage_note": "ar:note", "examples": [f"ar:{example}"]},
        "pt-BR": {"definition": "pt:def", "usage_note": "pt:note", "examples": [f"pt:{example}"]},
        "ja": {"definition": "ja:def", "usage_note": "ja:note", "examples": [f"ja:{example}"]},
    }


class PhraseEnrichmentSchemaTests(unittest.TestCase):
    def test_schema_uses_bounded_senses_contract(self) -> None:
        schema = build_phrase_enrichment_response_schema()

        self.assertIn("senses", schema["schema"]["properties"])
        self.assertEqual(schema["schema"]["properties"]["senses"]["minItems"], 1)
        self.assertEqual(schema["schema"]["properties"]["senses"]["maxItems"], 2)
        sense_properties = schema["schema"]["properties"]["senses"]["items"]["properties"]
        self.assertIn("definition", sense_properties)
        self.assertIn("part_of_speech", sense_properties)
        self.assertIn("examples", sense_properties)
        self.assertIn("grammar_patterns", sense_properties)
        self.assertIn("usage_note", sense_properties)
        self.assertIn("translations", sense_properties)
        self.assertEqual(
            sense_properties["examples"]["items"]["properties"]["difficulty"]["enum"],
            ["A1", "A2", "B1", "B2", "C1", "C2"],
        )

    def test_normalize_phrase_enrichment_payload_normalizes_sense_rows(self) -> None:
        normalized = normalize_phrase_enrichment_payload(
            {
                "phrase_kind": "idiom",
                "confidence": 0.87,
                "senses": [
                    {
                        "definition": "to wish someone good luck",
                        "part_of_speech": "phrase",
                        "examples": [{"sentence": "People say break a leg before a performance.", "difficulty": "B1"}],
                        "grammar_patterns": ["say + phrase"],
                        "usage_note": "Usually said before a performance.",
                        "translations": _translations("People say break a leg before a performance."),
                    }
                ],
            }
        )

        self.assertEqual(normalized["phrase_kind"], "idiom")
        self.assertEqual(normalized["confidence"], 0.87)
        self.assertEqual(normalized["senses"][0]["part_of_speech"], "phrase")
        self.assertEqual(normalized["senses"][0]["examples"][0].sentence, "People say break a leg before a performance.")

    def test_normalize_phrase_enrichment_payload_rejects_unknown_phrase_kind(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "phrase_kind"):
            normalize_phrase_enrichment_payload(
                {
                    "phrase_kind": "collocation",
                    "confidence": 0.87,
                    "senses": [
                        {
                            "definition": "x",
                            "part_of_speech": "phrase",
                            "examples": [{"sentence": "x", "difficulty": "A1"}],
                            "grammar_patterns": [],
                            "usage_note": "x",
                            "translations": _translations("x"),
                        }
                    ],
                }
            )

    def test_normalize_phrase_enrichment_payload_requires_examples_per_sense(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "examples"):
            normalize_phrase_enrichment_payload(
                {
                    "phrase_kind": "phrasal_verb",
                    "confidence": 0.87,
                    "senses": [
                        {
                            "definition": "to leave the ground",
                            "part_of_speech": "verb",
                            "examples": [],
                            "grammar_patterns": ["subject + take off"],
                            "usage_note": "Common for planes.",
                            "translations": _translations("placeholder"),
                        }
                    ],
                }
            )

    def test_normalize_phrase_enrichment_payload_rejects_more_than_two_senses(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "at most 2"):
            normalize_phrase_enrichment_payload(
                {
                    "phrase_kind": "phrasal_verb",
                    "confidence": 0.87,
                    "senses": [
                        {
                            "definition": "sense 1",
                            "part_of_speech": "verb",
                            "examples": [{"sentence": "one", "difficulty": "A1"}],
                            "grammar_patterns": [],
                            "usage_note": "one",
                            "translations": _translations("one"),
                        },
                        {
                            "definition": "sense 2",
                            "part_of_speech": "verb",
                            "examples": [{"sentence": "two", "difficulty": "A1"}],
                            "grammar_patterns": [],
                            "usage_note": "two",
                            "translations": _translations("two"),
                        },
                        {
                            "definition": "sense 3",
                            "part_of_speech": "verb",
                            "examples": [{"sentence": "three", "difficulty": "A1"}],
                            "grammar_patterns": [],
                            "usage_note": "three",
                            "translations": _translations("three"),
                        },
                    ],
                }
            )

    def test_normalize_phrase_enrichment_payload_aligns_translation_examples_to_english_count(self) -> None:
        normalized = normalize_phrase_enrichment_payload(
            {
                "phrase_kind": "idiom",
                "confidence": 0.87,
                "senses": [
                    {
                        "definition": "to wish someone good luck",
                        "part_of_speech": "phrase",
                        "examples": [
                            {"sentence": "Break a leg tonight.", "difficulty": "B1"},
                            {"sentence": "They told me to break a leg before the show.", "difficulty": "B1"},
                        ],
                        "grammar_patterns": ["say + phrase"],
                        "usage_note": "Usually said before a performance.",
                        "translations": _translations("Break a leg tonight."),
                    }
                ],
            }
        )

        self.assertEqual(len(normalized["senses"][0]["translations"]["es"]["examples"]), 2)
        self.assertEqual(
            normalized["senses"][0]["translations"]["es"]["examples"],
            ["es:Break a leg tonight.", "es:Break a leg tonight."],
        )

    def test_normalize_phrase_enrichment_payload_rejects_control_characters(self) -> None:
        payload = {
            "phrase_kind": "idiom",
            "confidence": 0.87,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "Break a leg tonight.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Usually said before a performance.",
                    "translations": _translations("Break a leg tonight."),
                }
            ],
        }
        payload["senses"][0]["translations"]["pt-BR"]["usage_note"] = "frequ\x00eancia"

        with self.assertRaisesRegex(RuntimeError, "control character"):
            normalize_phrase_enrichment_payload(payload)
