from __future__ import annotations

import unittest

from tools.lexicon.review_prep import build_review_prep_rows, build_review_queue_rows


def _phonetics() -> dict[str, object]:
    return {
        "us": {"ipa": "/bæŋk/", "confidence": 0.99},
        "uk": {"ipa": "/bæŋk/", "confidence": 0.98},
        "au": {"ipa": "/bæŋk/", "confidence": 0.97},
    }


def _compiled_word_row() -> dict[str, object]:
    return {
        "schema_version": "1.1.0",
        "entry_id": "word:bank",
        "entry_type": "word",
        "normalized_form": "bank",
        "source_provenance": [{"source": "snapshot"}],
        "entity_category": "general",
        "word": "bank",
        "part_of_speech": ["noun"],
        "cefr_level": "B1",
        "frequency_rank": 100,
        "forms": {"plural_forms": ["banks"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
        "senses": [
            {
                "sense_id": "sense-bank-1",
                "definition": "a financial institution",
                "examples": [{"sentence": "She went to the bank.", "difficulty": "A1"}],
                "translations": {
                    "zh-Hans": {"definition": "银行", "usage_note": "常见词义", "examples": ["她去了银行。"]},
                    "es": {"definition": "banco", "usage_note": "uso comun", "examples": ["Ella fue al banco."]},
                    "ar": {"definition": "بنك", "usage_note": "معنى شائع", "examples": ["ذهبت إلى البنك."]},
                    "pt-BR": {"definition": "banco", "usage_note": "uso comum", "examples": ["Ela foi ao banco."]},
                    "ja": {"definition": "銀行", "usage_note": "よくある意味", "examples": ["彼女は銀行に行った。"]},
                },
            }
        ],
        "confusable_words": [],
        "phonetics": _phonetics(),
        "generated_at": "2026-03-22T00:00:00Z",
    }


def _compiled_phrase_row_with_warning() -> dict[str, object]:
    return {
        "schema_version": "1.1.0",
        "entry_id": "phrase:break-a-leg",
        "entry_type": "phrase",
        "normalized_form": "break a leg",
        "source_provenance": [{"source": "phrase_seed"}],
        "entity_category": "general",
        "word": "break a leg",
        "part_of_speech": ["idiom"],
        "cefr_level": "B1",
        "frequency_rank": 5000,
        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
        "senses": [{
            "sense_id": "phrase-1",
            "definition": "good luck",
            "part_of_speech": "phrase",
            "examples": [{"sentence": "Break a leg tonight.", "difficulty": "A1"}],
            "grammar_patterns": ["say + phrase"],
            "usage_note": "Used before a performance.",
            "translations": {
                "zh-Hans": {"definition": "祝你好运", "usage_note": "演出前常说", "examples": ["今晚祝你好运。"]},
                "es": {"definition": "buena suerte", "usage_note": "se dice antes de actuar", "examples": ["Buena suerte esta noche."]},
                "ar": {"definition": "حظا سعيدا", "usage_note": "تقال قبل العرض", "examples": ["حظا سعيدا الليلة."]},
                "pt-BR": {"definition": "boa sorte", "usage_note": "dito antes de se apresentar", "examples": ["Boa sorte esta noite."]},
                "ja": {"definition": "頑張って", "usage_note": "公演前によく言う", "examples": ["今夜頑張って。"]},
            },
        }],
        "confusable_words": [],
        "generated_at": "2026-03-22T00:00:00Z",
        "display_form": "break a leg",
        "phrase_kind": "idiom",
        "seed_metadata": {"raw_reviewed_as": "idiom"},
    }


def _compiled_reference_row_with_warning() -> dict[str, object]:
    return {
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
        "generated_at": "2026-03-22T00:00:00Z",
        "reference_type": "country",
        "display_form": "Australia",
        "translation_mode": "localized",
        "brief_description": "A country in the Southern Hemisphere.",
        "pronunciation": "/ɔˈstreɪliə/",
        "localized_display_form": {"es": "Australia"},
        "localized_brief_description": {"es": "Pais del hemisferio sur."},
        "learner_tip": "Stress is on STRAY.",
        "localizations": [],
    }


class ReviewPrepTests(unittest.TestCase):
    def test_build_review_prep_rows_derives_warnings_and_priority_for_compiled_rows(self) -> None:
        rows = build_review_prep_rows(
            [
                _compiled_word_row(),
                _compiled_phrase_row_with_warning(),
                _compiled_reference_row_with_warning(),
            ],
            origin="realtime",
        )

        self.assertEqual(rows[0]["verdict"], "pass")
        self.assertEqual(rows[0]["review_priority"], 100)
        self.assertEqual(rows[0]["warning_labels"], [])

        self.assertEqual(rows[1]["verdict"], "pass")
        self.assertEqual(rows[1]["review_priority"], 100)
        self.assertEqual(rows[1]["warning_labels"], [])
        self.assertEqual(rows[1]["review_summary"]["primary_example"], "Break a leg tonight.")

        self.assertEqual(rows[2]["verdict"], "fail")
        self.assertEqual(rows[2]["warning_labels"], ["missing_localizations"])

    def test_build_review_prep_rows_is_origin_agnostic_for_equivalent_compiled_rows(self) -> None:
        realtime_rows = build_review_prep_rows([_compiled_word_row()], origin="realtime")
        batch_rows = build_review_prep_rows([_compiled_word_row()], origin="batch")

        self.assertEqual(realtime_rows[0]["warning_labels"], batch_rows[0]["warning_labels"])
        self.assertEqual(realtime_rows[0]["review_priority"], batch_rows[0]["review_priority"])
        self.assertEqual(realtime_rows[0]["verdict"], batch_rows[0]["verdict"])

    def test_build_review_prep_rows_uses_batch_status_without_compiled_payload(self) -> None:
        rows = build_review_prep_rows(
            [
                {
                    "custom_id": "phrase:lexicon:s2:attempt1",
                    "entry_type": "phrase",
                    "entry_kind": "phrase",
                    "entry_id": "s2",
                    "status": "failed",
                    "validation_status": "invalid",
                    "error_detail": "bad payload",
                }
            ],
            origin="batch",
        )

        self.assertEqual(rows[0]["verdict"], "fail")
        self.assertEqual(rows[0]["reasons"], ["status=failed", "validation_status=invalid"])
        self.assertEqual(rows[0]["review_notes"], "bad payload")

    def test_build_review_queue_rows_only_keeps_failed_rows(self) -> None:
        verdict_rows = build_review_prep_rows(
            [
                _compiled_word_row(),
                _compiled_phrase_row_with_warning(),
            ],
            origin="realtime",
        )

        queue_rows = build_review_queue_rows(verdict_rows)

        self.assertEqual(queue_rows, [])
