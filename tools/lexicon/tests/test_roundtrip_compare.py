import unittest

from tools.lexicon.roundtrip_compare import compare_compiled_rows


class RoundtripCompareTests(unittest.TestCase):
    def test_compare_compiled_rows_ignores_empty_verb_form_placeholders(self) -> None:
        source_rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "all",
                "language": "en",
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {
                        "base": "",
                        "past": "",
                        "gerund": "",
                    },
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [],
            }
        ]
        exported_rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "all",
                "language": "en",
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [],
            }
        ]

        summary = compare_compiled_rows(source_rows, exported_rows)

        self.assertEqual(summary["missing_row_ids"], [])
        self.assertEqual(summary["added_row_ids"], [])
        self.assertEqual(summary["mismatched_rows"], [])

    def test_compare_compiled_rows_tracks_translation_diffs_explicitly(self) -> None:
        source_rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "forms": {},
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "examples": ["Eu nao tenho tempo hoje."],
                            }
                        },
                    }
                ],
            }
        ]
        exported_rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "forms": {},
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "examples": [],
                            }
                        },
                    }
                ],
            }
        ]

        summary = compare_compiled_rows(source_rows, exported_rows)

        self.assertEqual(summary["translation_definition_diffs"], [])
        self.assertEqual(summary["translation_example_diffs"], ["word:time:en:sense[0]:pt-BR"])
        self.assertEqual(summary["translation_definition_count"], 1)
        self.assertEqual(summary["exported_translation_definition_count"], 1)
        self.assertEqual(summary["translation_example_count"], 1)
        self.assertEqual(summary["exported_translation_example_count"], 0)


if __name__ == "__main__":
    unittest.main()
