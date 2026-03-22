from __future__ import annotations

import unittest

from tools.lexicon.contracts import ALLOWED_CEFR_LEVELS, ALLOWED_REGISTERS, REQUIRED_TRANSLATION_LOCALES
from tools.lexicon.schemas.compiled_export_schema import build_compiled_export_schema
from tools.lexicon.schemas.phrase_enrichment_schema import build_phrase_enrichment_response_schema
from tools.lexicon.schemas.qc_verdict_schema import build_qc_verdict_schema
from tools.lexicon.schemas.reference_entry_schema import build_reference_entry_response_schema
from tools.lexicon.schemas.word_enrichment_schema import (
    build_single_sense_response_schema,
    build_word_enrichment_response_schema,
)


class ContractSchemaTests(unittest.TestCase):
    def test_shared_contract_constants_are_available(self) -> None:
        self.assertEqual(
            tuple(REQUIRED_TRANSLATION_LOCALES),
            ("zh-Hans", "es", "ar", "pt-BR", "ja"),
        )
        self.assertIn("A1", ALLOWED_CEFR_LEVELS)
        self.assertIn("neutral", ALLOWED_REGISTERS)

    def test_word_schema_exposes_existing_response_shape(self) -> None:
        schema = build_word_enrichment_response_schema()

        self.assertEqual(schema["name"], "lexicon_enrichment_word")
        self.assertTrue(schema["strict"])
        self.assertEqual(
            schema["schema"]["properties"]["decision"]["enum"],
            ["discard", "keep_derived_special", "keep_standard"],
        )
        self.assertIn(
            "part_of_speech",
            schema["schema"]["properties"]["senses"]["items"]["properties"],
        )
        self.assertIn(
            "sense_kind",
            schema["schema"]["properties"]["senses"]["items"]["properties"],
        )

    def test_single_sense_schema_is_available(self) -> None:
        schema = build_single_sense_response_schema()

        self.assertEqual(schema["name"], "lexicon_enrichment_single_sense")
        self.assertTrue(schema["strict"])
        self.assertIn("translations", schema["schema"]["properties"])

    def test_phrase_schema_is_available(self) -> None:
        schema = build_phrase_enrichment_response_schema()

        self.assertEqual(schema["name"], "lexicon_enrichment_phrase")
        self.assertTrue(schema["strict"])
        self.assertIn("phrase_kind", schema["schema"]["properties"])
        self.assertIn("senses", schema["schema"]["properties"])

    def test_reference_schema_is_available(self) -> None:
        schema = build_reference_entry_response_schema()

        self.assertEqual(schema["name"], "lexicon_reference_entry")
        self.assertTrue(schema["strict"])
        for field in (
            "reference_type",
            "display_form",
            "translation_mode",
            "brief_description",
            "pronunciation",
        ):
            self.assertIn(field, schema["schema"]["properties"])

    def test_qc_verdict_schema_is_available(self) -> None:
        schema = build_qc_verdict_schema()

        self.assertEqual(schema["name"], "lexicon_qc_verdict")
        self.assertTrue(schema["strict"])
        self.assertIn("verdict", schema["schema"]["properties"])

    def test_compiled_export_schema_is_available(self) -> None:
        schema = build_compiled_export_schema()

        self.assertEqual(schema["name"], "lexicon_compiled_export_row")
        self.assertTrue(schema["strict"])
        self.assertIn("schema_version", schema["schema"]["properties"])
        self.assertIn("senses", schema["schema"]["properties"])
