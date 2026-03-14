import unittest

from tools.lexicon.audit_30k_semantics import _risk_buckets


class Audit30kSemanticsTests(unittest.TestCase):
    def test_risk_buckets_ignore_surface_suffix_false_positives(self) -> None:
        buckets = _risk_buckets(
            lexeme={
                "lemma": "business",
                "wordfreq_rank": 244000,
                "is_wordnet_backed": True,
                "entity_category": "general",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": ["occupation", "clientele"],
                "variant_type": "self",
            },
            entry={"source_forms": ["business"]},
        )

        self.assertNotIn("lexicalized_plural_candidate", buckets)
        self.assertNotIn("plural_morph_candidate", buckets)

    def test_risk_buckets_keep_real_plural_candidates(self) -> None:
        buckets = _risk_buckets(
            lexeme={
                "lemma": "days",
                "wordfreq_rank": 239000,
                "is_wordnet_backed": True,
                "entity_category": "general",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": ["day"],
                "variant_type": "self",
            },
            entry={"source_forms": ["days"]},
        )

        self.assertIn("plural_morph_candidate", buckets)
        self.assertIn("lexicalized_plural_candidate", buckets)

    def test_risk_buckets_categorize_contractions_and_possessives_separately(self) -> None:
        contraction_buckets = _risk_buckets(
            lexeme={
                "lemma": "it's",
                "wordfreq_rank": 167000,
                "is_wordnet_backed": False,
                "entity_category": "general",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": [],
                "variant_type": "self",
            },
            entry={"source_forms": ["it's"]},
        )
        possessive_buckets = _risk_buckets(
            lexeme={
                "lemma": "people's",
                "wordfreq_rank": 260000,
                "is_wordnet_backed": False,
                "entity_category": "general",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": ["people"],
                "variant_type": "self",
            },
            entry={"source_forms": ["people's"]},
        )

        self.assertIn("common_contraction", contraction_buckets)
        self.assertNotIn("possessive_surface_form", contraction_buckets)
        self.assertIn("possessive_surface_form", possessive_buckets)
        self.assertNotIn("common_contraction", possessive_buckets)

    def test_risk_buckets_ignore_non_matching_er_suffix_words(self) -> None:
        buckets = _risk_buckets(
            lexeme={
                "lemma": "other",
                "wordfreq_rank": 184000,
                "is_wordnet_backed": True,
                "entity_category": "general",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": ["early"],
                "variant_type": "self",
            },
            entry={"source_forms": ["other"]},
        )

        self.assertNotIn("derived_form_candidate", buckets)
        self.assertNotIn("derived_morph_candidate", buckets)

    def test_risk_buckets_flag_non_general_entity_rows(self) -> None:
        buckets = _risk_buckets(
            lexeme={
                "lemma": "kinshasa",
                "wordfreq_rank": 39386,
                "is_wordnet_backed": True,
                "entity_category": "place",
            },
            variant={
                "decision": "keep_separate",
                "candidate_forms": [],
                "variant_type": "self",
            },
            entry={"source_forms": ["kinshasa"]},
        )

        self.assertIn("non_general_entity", buckets)


if __name__ == "__main__":
    unittest.main()
