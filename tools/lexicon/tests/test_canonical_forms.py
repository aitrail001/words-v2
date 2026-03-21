import unittest
from unittest.mock import patch

from tools.lexicon.build_base import build_base_records
from tools.lexicon.canonical_forms import _suffix_candidates


class CanonicalFormsTests(unittest.TestCase):
    def test_build_base_records_collapses_plural_surface_form_to_canonical_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "things": 120,
                "thing": 40,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"things", "thing"}:
                return [
                    {
                        "wn_synset_id": "thing.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an object, idea, event, or fact",
                        "canonical_label": "thing",
                    }
                ]
            if word == "thing":
                return [
                    {
                        "wn_synset_id": "thing.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an object, idea, event, or fact",
                        "canonical_label": "thing",
                    }
                ]
            return []

        result = build_base_records(
            words=["things"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["thing"])
        self.assertEqual([record.canonical_form for record in result.canonical_entries], ["thing"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "things")
        self.assertEqual(result.canonical_variants[0].canonical_form, "thing")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_common_verb_inflections(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "gives": 150,
                "giving": 140,
                "give": 20,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"gives", "giving", "give"}:
                return [
                    {
                        "wn_synset_id": "give.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to hand something to someone",
                        "canonical_label": "give",
                    }
                ]
            return []

        result = build_base_records(
            words=["gives", "giving"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["give"])
        self.assertEqual(sorted(record.surface_form for record in result.canonical_variants), ["gives", "giving"])
        self.assertTrue(all(record.canonical_form == "give" for record in result.canonical_variants))

    def test_build_base_records_applies_force_keep_separate_anomaly_override(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "angeles": 100,
                "angel": 80,
            }.get(word, 999_999)

        def sense_provider(word: str):
            return []

        with patch(
            "tools.lexicon.canonical_forms._load_canonical_anomaly_overrides",
            return_value={
                "force_keep_separate": {
                    "angeles": {"reason": "place_name_like"}
                },
                "force_collapse_to_canonical": {},
            },
            create=True,
        ):
            result = build_base_records(
                words=["angeles"],
                snapshot_id="lexicon-20260314-wordnet-wordfreq",
                created_at="2026-03-14T00:00:00Z",
                rank_provider=rank_provider,
                sense_provider=sense_provider,
            )

        self.assertEqual([record.lemma for record in result.lexemes], ["angeles"])
        self.assertEqual(result.canonical_variants[0].decision, "keep_separate")
        self.assertEqual(result.canonical_variants[0].canonical_form, "angeles")
        self.assertEqual(result.ambiguous_forms, [])

    def test_build_base_records_applies_force_collapse_anomaly_override(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "rupees": 220,
                "rupee": 240,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "rupees":
                return [
                    {
                        "wn_synset_id": "indian_rupee.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "the currency of India",
                        "canonical_label": "Indian rupee",
                    }
                ]
            return []

        with patch(
            "tools.lexicon.canonical_forms._load_canonical_anomaly_overrides",
            return_value={
                "force_keep_separate": {},
                "force_collapse_to_canonical": {
                    "rupees": {"canonical_form": "rupee", "reason": "regular_plural_exception"}
                },
            },
            create=True,
        ):
            result = build_base_records(
                words=["rupees"],
                snapshot_id="lexicon-20260314-wordnet-wordfreq",
                created_at="2026-03-14T00:00:00Z",
                rank_provider=rank_provider,
                sense_provider=sense_provider,
            )

        self.assertEqual([record.lemma for record in result.lexemes], ["rupee"])
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")
        self.assertEqual(result.canonical_variants[0].canonical_form, "rupee")
        self.assertEqual(result.ambiguous_forms, [])

    def test_build_base_records_applies_force_collapse_anomaly_override_after_plural_candidate_pruning(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "perks": 220,
                "perk": 240,
            }.get(word, 999_999)

        def sense_provider(word: str):
            return []

        with patch(
            "tools.lexicon.canonical_forms._load_canonical_anomaly_overrides",
            return_value={
                "force_keep_separate": {},
                "force_collapse_to_canonical": {
                    "perks": {"canonical_form": "perk", "reason": "regular_plural_exception"}
                },
            },
            create=True,
        ):
            result = build_base_records(
                words=["perks"],
                snapshot_id="lexicon-20260316-perks-anomaly-regression",
                created_at="2026-03-16T00:00:00Z",
                rank_provider=rank_provider,
                sense_provider=sense_provider,
            )

        self.assertEqual([record.lemma for record in result.lexemes], ["perk"])
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")
        self.assertEqual(result.canonical_variants[0].canonical_form, "perk")
        self.assertEqual(result.ambiguous_forms, [])

    def test_build_base_records_keeps_lexicalized_irregular_surface_form(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "left": 15,
                "leave": 12,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "left":
                return [
                    {
                        "wn_synset_id": "left.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "on the side of the body opposite the right side",
                        "canonical_label": "left",
                    },
                    {
                        "wn_synset_id": "leave.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to go away from a place",
                        "canonical_label": "leave",
                    },
                ]
            if word == "leave":
                return [
                    {
                        "wn_synset_id": "leave.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to go away from a place",
                        "canonical_label": "leave",
                    }
                ]
            return []

        result = build_base_records(
            words=["left"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["left"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "left")
        self.assertEqual(result.canonical_variants[0].canonical_form, "left")
        self.assertEqual(result.canonical_variants[0].linked_canonical_form, "leave")
        self.assertEqual(result.canonical_variants[0].decision, "keep_both_linked")

    def test_build_base_records_keeps_lexicalized_plural_common_nouns_separate(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "clothes": 70,
                "clothe": 120,
                "goods": 80,
                "good": 30,
                "spirits": 90,
                "spirit": 40,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "clothes":
                return [
                    {
                        "wn_synset_id": "apparel.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "clothing in general",
                        "canonical_label": "apparel",
                    }
                ]
            if word == "goods":
                return [
                    {
                        "wn_synset_id": "commodity.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "articles of commerce",
                        "canonical_label": "commodity",
                    }
                ]
            if word == "spirits":
                return [
                    {
                        "wn_synset_id": "liquor.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "distilled alcoholic drink",
                        "canonical_label": "liquor",
                    }
                ]
            return []

        result = build_base_records(
            words=["clothes", "goods", "spirits"],
            snapshot_id="lexicon-20260314-lexicalized-plural-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["clothes", "goods", "spirits"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        for surface_form in ("clothes", "goods", "spirits"):
            self.assertEqual(variants[surface_form].canonical_form, surface_form)
            self.assertEqual(variants[surface_form].decision, "keep_separate")

    def test_build_base_records_collapses_compound_irregular_men_plural(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "middlemen": 39479,
                "middleman": 500000,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"middlemen", "middleman"}:
                return [
                    {
                        "wn_synset_id": "middleman.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an intermediary between two parties",
                        "canonical_label": "middleman",
                    }
                ]
            return []

        result = build_base_records(
            words=["middlemen"],
            snapshot_id="lexicon-20260314-compound-irregular-men",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["middleman"])
        self.assertEqual(result.canonical_variants[0].surface_form, "middlemen")
        self.assertEqual(result.canonical_variants[0].canonical_form, "middleman")

    def test_build_base_records_collapses_irregular_plural_to_base_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "children": 40,
                "child": 20,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"children", "child"}:
                return [
                    {
                        "wn_synset_id": "child.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a young person",
                        "canonical_label": "child",
                    }
                ]
            return []

        result = build_base_records(
            words=["children"],
            snapshot_id="lexicon-20260314-irregular-plural-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["child"])
        self.assertEqual(result.canonical_variants[0].surface_form, "children")
        self.assertEqual(result.canonical_variants[0].canonical_form, "child")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_compound_irregular_plural_to_base_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "grandchildren": 60,
                "grandchild": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"grandchildren", "grandchild"}:
                return [
                    {
                        "wn_synset_id": "grandchild.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a child of one's child",
                        "canonical_label": "grandchild",
                    }
                ]
            return []

        result = build_base_records(
            words=["grandchildren"],
            snapshot_id="lexicon-20260314-irregular-plural-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["grandchild"])
        self.assertEqual(result.canonical_variants[0].surface_form, "grandchildren")
        self.assertEqual(result.canonical_variants[0].canonical_form, "grandchild")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_irregular_verb_form_to_base_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "ate": 80,
                "eat": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"ate", "eat"}:
                return [
                    {
                        "wn_synset_id": "eat.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to consume food",
                        "canonical_label": "eat",
                    }
                ]
            return []

        result = build_base_records(
            words=["ate"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["eat"])
        self.assertEqual(result.canonical_variants[0].surface_form, "ate")
        self.assertEqual(result.canonical_variants[0].canonical_form, "eat")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_additional_irregular_verb_form_to_base_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "did": 80,
                "do": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"did", "do"}:
                return [
                    {
                        "wn_synset_id": "do.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to perform an action",
                        "canonical_label": "do",
                    }
                ]
            return []

        result = build_base_records(
            words=["did"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["do"])
        self.assertEqual(result.canonical_variants[0].surface_form, "did")
        self.assertEqual(result.canonical_variants[0].canonical_form, "do")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_multiple_high_confidence_irregular_verb_forms(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "got": 80,
                "get": 30,
                "heard": 85,
                "hear": 35,
                "led": 90,
                "lead": 40,
                "met": 95,
                "meet": 45,
            }.get(word, 999_999)

        def sense_provider(word: str):
            mapping = {
                "got": ("get.v.01", "to receive or obtain", "get"),
                "get": ("get.v.01", "to receive or obtain", "get"),
                "heard": ("hear.v.01", "to perceive by hearing", "hear"),
                "hear": ("hear.v.01", "to perceive by hearing", "hear"),
                "led": ("lead.v.01", "to guide or direct", "lead"),
                "lead": ("lead.v.01", "to guide or direct", "lead"),
                "met": ("meet.v.01", "to come together with someone", "meet"),
                "meet": ("meet.v.01", "to come together with someone", "meet"),
            }
            if word not in mapping:
                return []
            synset_id, gloss, label = mapping[word]
            return [
                {
                    "wn_synset_id": synset_id,
                    "part_of_speech": "verb",
                    "canonical_gloss": gloss,
                    "canonical_label": label,
                }
            ]

        result = build_base_records(
            words=["got", "heard", "led", "met"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["get", "hear", "lead", "meet"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["got"].canonical_form, "get")
        self.assertEqual(variants["heard"].canonical_form, "hear")
        self.assertEqual(variants["led"].canonical_form, "lead")
        self.assertEqual(variants["met"].canonical_form, "meet")
        self.assertTrue(all(variant.decision == "collapse_to_canonical" for variant in variants.values()))

    def test_build_base_records_collapses_additional_simple_irregular_past_forms(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "became": 80,
                "become": 30,
                "began": 82,
                "begin": 32,
                "chose": 84,
                "choose": 34,
                "kept": 86,
                "keep": 36,
                "told": 88,
                "tell": 38,
                "understood": 90,
                "understand": 40,
            }.get(word, 999_999)

        def sense_provider(word: str):
            mapping = {
                "became": ("become.v.01", "to come to be", "become"),
                "become": ("become.v.01", "to come to be", "become"),
                "began": ("begin.v.01", "to start", "begin"),
                "begin": ("begin.v.01", "to start", "begin"),
                "chose": ("choose.v.01", "to select", "choose"),
                "choose": ("choose.v.01", "to select", "choose"),
                "kept": ("keep.v.01", "to retain or continue to have", "keep"),
                "keep": ("keep.v.01", "to retain or continue to have", "keep"),
                "told": ("tell.v.01", "to communicate in words", "tell"),
                "tell": ("tell.v.01", "to communicate in words", "tell"),
                "understood": ("understand.v.01", "to comprehend", "understand"),
                "understand": ("understand.v.01", "to comprehend", "understand"),
            }
            if word not in mapping:
                return []
            synset_id, gloss, label = mapping[word]
            return [
                {
                    "wn_synset_id": synset_id,
                    "part_of_speech": "verb",
                    "canonical_gloss": gloss,
                    "canonical_label": label,
                }
            ]

        result = build_base_records(
            words=["became", "began", "chose", "kept", "told", "understood"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(
            sorted(record.lemma for record in result.lexemes),
            ["become", "begin", "choose", "keep", "tell", "understand"],
        )
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["became"].canonical_form, "become")
        self.assertEqual(variants["began"].canonical_form, "begin")
        self.assertEqual(variants["chose"].canonical_form, "choose")
        self.assertEqual(variants["kept"].canonical_form, "keep")
        self.assertEqual(variants["told"].canonical_form, "tell")
        self.assertEqual(variants["understood"].canonical_form, "understand")
        self.assertTrue(all(variant.decision == "collapse_to_canonical" for variant in variants.values()))

    def test_build_base_records_uses_irregular_plural_mapping_instead_of_wrong_suffix_guess(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "diagnoses": 70,
                "diagnosis": 90,
                "diagnose": 60,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "diagnoses":
                return [
                    {
                        "wn_synset_id": "diagnosis.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "identification of a disease or problem",
                        "canonical_label": "diagnosis",
                    }
                ]
            if word == "diagnosis":
                return [
                    {
                        "wn_synset_id": "diagnosis.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "identification of a disease or problem",
                        "canonical_label": "diagnosis",
                    }
                ]
            if word == "diagnose":
                return [
                    {
                        "wn_synset_id": "diagnose.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to identify a disease or problem",
                        "canonical_label": "diagnose",
                    }
                ]
            return []

        result = build_base_records(
            words=["diagnoses"],
            snapshot_id="lexicon-20260314-irregular-plural-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["diagnosis"])
        self.assertEqual(result.canonical_variants[0].canonical_form, "diagnosis")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_uses_irregular_verb_mapping_instead_of_wrong_suffix_guess(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "bled": 70,
                "bleed": 90,
                "bl": 60,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word in {"bled", "bleed"}:
                return [
                    {
                        "wn_synset_id": "bleed.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to lose blood",
                        "canonical_label": "bleed",
                    }
                ]
            return []

        result = build_base_records(
            words=["bled"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["bleed"])
        self.assertEqual(result.canonical_variants[0].canonical_form, "bleed")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_keeps_irregular_comparative_with_distinct_meaning_linked(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "elder": 70,
                "old": 20,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "elder":
                return [
                    {
                        "wn_synset_id": "elder.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "older in rank or status, especially within a family",
                        "canonical_label": "elder",
                    },
                    {
                        "wn_synset_id": "old.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "advanced in age",
                        "canonical_label": "old",
                    },
                ]
            if word == "old":
                return [
                    {
                        "wn_synset_id": "old.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "advanced in age",
                        "canonical_label": "old",
                    }
                ]
            return []

        result = build_base_records(
            words=["elder"],
            snapshot_id="lexicon-20260314-irregular-comparative-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["elder"])
        self.assertEqual(result.canonical_variants[0].canonical_form, "elder")
        self.assertEqual(result.canonical_variants[0].linked_canonical_form, "old")
        self.assertEqual(result.canonical_variants[0].decision, "keep_both_linked")

    def test_build_base_records_does_not_collapse_semantic_neighbor_about(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "almost": 60,
                "about": 25,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "almost":
                return [
                    {
                        "wn_synset_id": "about.r.01",
                        "part_of_speech": "adverb",
                        "canonical_gloss": "approximately or nearly",
                        "canonical_label": "about",
                    }
                ]
            if word == "about":
                return [
                    {
                        "wn_synset_id": "about.r.01",
                        "part_of_speech": "adverb",
                        "canonical_gloss": "approximately or nearly",
                        "canonical_label": "about",
                    }
                ]
            return []

        result = build_base_records(
            words=["almost"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["almost"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "almost")
        self.assertEqual(result.canonical_variants[0].canonical_form, "almost")
        self.assertEqual(result.canonical_variants[0].decision, "keep_separate")

    def test_build_base_records_does_not_collapse_semantic_neighbor_full(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "total": 70,
                "full": 40,
                "sum": 140,
                "entire": 130,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "total":
                return [
                    {
                        "wn_synset_id": "sum.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "the whole amount",
                        "canonical_label": "sum",
                    },
                    {
                        "wn_synset_id": "entire.s.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "complete in extent",
                        "canonical_label": "entire",
                    },
                    {
                        "wn_synset_id": "full.s.06",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "constituting the full quantity",
                        "canonical_label": "full",
                    },
                ]
            if word in {"full", "sum", "entire"}:
                return [
                    {
                        "wn_synset_id": f"{word}.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": word,
                        "canonical_label": word,
                    }
                ]
            return []

        result = build_base_records(
            words=["total"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["total"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "total")
        self.assertEqual(result.canonical_variants[0].canonical_form, "total")
        self.assertEqual(result.canonical_variants[0].decision, "keep_separate")

    def test_build_base_records_keeps_morph_related_surface_form_with_own_meaning(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "meeting": 80,
                "meet": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "meeting":
                return [
                    {
                        "wn_synset_id": "meeting.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an event where people gather",
                        "canonical_label": "meeting",
                    },
                    {
                        "wn_synset_id": "meet.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to come together with someone",
                        "canonical_label": "meet",
                    },
                ]
            if word == "meet":
                return [
                    {
                        "wn_synset_id": "meet.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to come together with someone",
                        "canonical_label": "meet",
                    }
                ]
            return []

        result = build_base_records(
            words=["meeting"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["meeting"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "meeting")
        self.assertEqual(result.canonical_variants[0].canonical_form, "meeting")
        self.assertEqual(result.canonical_variants[0].decision, "keep_both_linked")
        self.assertEqual(result.canonical_variants[0].linked_canonical_form, "meet")

    def test_build_base_records_keeps_lexicalized_plural_with_own_meaning_separate(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "things": 120,
                "thing": 40,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "things":
                return [
                    {
                        "wn_synset_id": "things.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "personal effects or possessions",
                        "canonical_label": "things",
                    },
                    {
                        "wn_synset_id": "thing.n.08",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an entity that is not named specifically",
                        "canonical_label": "thing",
                    },
                ]
            if word == "thing":
                return [
                    {
                        "wn_synset_id": "thing.n.08",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an entity that is not named specifically",
                        "canonical_label": "thing",
                    }
                ]
            return []

        result = build_base_records(
            words=["things"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["things"])
        self.assertEqual(result.canonical_variants[0].surface_form, "things")
        self.assertEqual(result.canonical_variants[0].canonical_form, "things")
        self.assertEqual(result.canonical_variants[0].decision, "keep_separate")
        self.assertIsNone(result.canonical_variants[0].linked_canonical_form)

    def test_build_base_records_prefers_morphology_backed_candidate_over_semantic_neighbor(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "growing": 120,
                "grow": 40,
                "increase": 10,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "growing":
                return [
                    {
                        "wn_synset_id": "increase.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to become larger",
                        "canonical_label": "increase",
                    }
                ]
            if word in {"grow", "increase"}:
                return [
                    {
                        "wn_synset_id": f"{word}.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": word,
                        "canonical_label": word,
                    }
                ]
            return []

        result = build_base_records(
            words=["growing"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["grow"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "growing")
        self.assertEqual(result.canonical_variants[0].canonical_form, "grow")
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")

    def test_build_base_records_does_not_link_weak_morphology_guess_without_label_support(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "glasses": 80,
                "glass": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "glasses":
                return [
                    {
                        "wn_synset_id": "spectacles.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "eyewear with lenses",
                        "canonical_label": "glasses",
                    }
                ]
            if word == "glass":
                return [
                    {
                        "wn_synset_id": "glass.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a hard brittle transparent solid",
                        "canonical_label": "glass",
                    }
                ]
            return []

        result = build_base_records(
            words=["glasses"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["glasses"])
        self.assertEqual(len(result.canonical_variants), 1)
        self.assertEqual(result.canonical_variants[0].surface_form, "glasses")
        self.assertEqual(result.canonical_variants[0].canonical_form, "glasses")
        self.assertEqual(result.canonical_variants[0].decision, "keep_separate")
        self.assertIsNone(result.canonical_variants[0].linked_canonical_form)

    def test_suffix_candidates_skip_invalid_short_chops_for_double_s_words(self) -> None:
        self.assertNotIn("pas", _suffix_candidates("pass"))
        self.assertNotIn("glas", _suffix_candidates("glass"))
        self.assertNotIn("clas", _suffix_candidates("class"))
        self.assertIn("thing", _suffix_candidates("things"))
        self.assertIn("give", _suffix_candidates("gives"))

    def test_build_base_records_filters_weak_plain_s_suffix_candidates_without_lexical_support(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "this": 10,
                "thi": 500,
                "his": 20,
                "hi": 300,
                "chris": 40,
                "chri": 999_999,
                "series": 50,
                "seri": 999_999,
                "sery": 999_999,
                "itunes": 60,
                "itun": 999_999,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "hi":
                return [
                    {
                        "wn_synset_id": "hello.n.01",
                        "part_of_speech": "interjection",
                        "canonical_gloss": "a greeting",
                        "canonical_label": "hello",
                    }
                ]
            return []

        result = build_base_records(
            words=["this", "his", "chris", "series", "itunes"],
            snapshot_id="lexicon-20260313-suffix-hardening",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["chris", "his", "itunes", "series", "this"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["this"].decision, "keep_separate")
        self.assertEqual(variants["this"].candidate_forms, [])
        self.assertEqual(variants["his"].decision, "keep_separate")
        self.assertEqual(variants["his"].candidate_forms, [])
        self.assertEqual(variants["chris"].decision, "keep_separate")
        self.assertEqual(variants["chris"].candidate_forms, [])
        self.assertEqual(variants["series"].decision, "keep_separate")
        self.assertEqual(variants["series"].candidate_forms, [])
        self.assertEqual(variants["itunes"].decision, "keep_separate")
        self.assertEqual(variants["itunes"].candidate_forms, [])

    def test_build_base_records_keeps_plain_s_suffix_candidates_with_lexical_support(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "things": 120,
                "thing": 40,
                "gives": 150,
                "give": 20,
                "pesos": 220,
                "peso": 240,
                "rupees": 250,
                "rupee": 260,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "things":
                return [
                    {
                        "wn_synset_id": "thing.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "an object",
                        "canonical_label": "thing",
                    }
                ]
            if word == "gives":
                return [
                    {
                        "wn_synset_id": "give.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to hand something to someone",
                        "canonical_label": "give",
                    }
                ]
            if word == "pesos":
                return [
                    {
                        "wn_synset_id": "mexican_peso.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "the currency of Mexico",
                        "canonical_label": "Mexican peso",
                    }
                ]
            if word == "rupees":
                return [
                    {
                        "wn_synset_id": "indian_rupee.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "the currency of India",
                        "canonical_label": "Indian rupee",
                    }
                ]
            return []

        result = build_base_records(
            words=["things", "gives", "pesos", "rupees"],
            snapshot_id="lexicon-20260313-suffix-hardening",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertIn("thing", variants["things"].candidate_forms)
        self.assertEqual(variants["things"].canonical_form, "thing")
        self.assertEqual(variants["things"].decision, "collapse_to_canonical")
        self.assertIn("give", variants["gives"].candidate_forms)
        self.assertEqual(variants["gives"].canonical_form, "give")
        self.assertEqual(variants["gives"].decision, "collapse_to_canonical")
        self.assertIn("peso", variants["pesos"].candidate_forms)
        self.assertEqual(variants["pesos"].canonical_form, "peso")
        self.assertEqual(variants["pesos"].decision, "collapse_to_canonical")
        self.assertIn("rupee", variants["rupees"].candidate_forms)
        self.assertEqual(variants["rupees"].canonical_form, "rupee")
        self.assertEqual(variants["rupees"].decision, "collapse_to_canonical")

    def test_build_base_records_filters_unsupported_non_plural_suffix_guesses(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "something": 70,
                "someth": 999_999,
                "somethe": 999_999,
                "anything": 75,
                "anyth": 999_999,
                "anythe": 999_999,
                "everything": 80,
                "everyth": 999_999,
                "everythe": 999_999,
                "during": 85,
                "dur": 999_999,
                "dure": 999_999,
                "whether": 90,
                "wheth": 999_999,
                "added": 95,
                "add": 20,
                "coming": 100,
                "come": 30,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "added":
                return [
                    {
                        "wn_synset_id": "add.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "make an addition",
                        "canonical_label": "add",
                    }
                ]
            if word == "coming":
                return [
                    {
                        "wn_synset_id": "come.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "move toward",
                        "canonical_label": "come",
                    }
                ]
            return []

        result = build_base_records(
            words=["something", "anything", "everything", "during", "whether", "added", "coming"],
            snapshot_id="lexicon-20260313-wordnet-wordfreq",
            created_at="2026-03-13T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        variants = {record.surface_form: record for record in result.canonical_variants}
        for surface_form in ("something", "anything", "everything", "during", "whether"):
            self.assertEqual(variants[surface_form].decision, "keep_separate")
            self.assertEqual(variants[surface_form].candidate_forms, [])
        self.assertEqual(variants["added"].canonical_form, "add")
        self.assertEqual(variants["added"].decision, "collapse_to_canonical")
        self.assertEqual(variants["coming"].canonical_form, "come")
        self.assertEqual(variants["coming"].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_possessive_surface_forms_to_base_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "people's": 140,
                "people": 30,
                "children's": 150,
                "children": 40,
                "men's": 160,
                "men": 50,
                "women's": 170,
                "women": 60,
                "today's": 160,
                "today": 60,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "people":
                return [
                    {
                        "wn_synset_id": "people.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "persons in general",
                        "canonical_label": "people",
                    }
                ]
            if word == "children":
                return [
                    {
                        "wn_synset_id": "children.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "young persons",
                        "canonical_label": "children",
                    }
                ]
            if word == "today":
                return [
                    {
                        "wn_synset_id": "today.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "the present day",
                        "canonical_label": "today",
                    }
                ]
            if word == "men":
                return [
                    {
                        "wn_synset_id": "man.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "adult male person",
                        "canonical_label": "man",
                    }
                ]
            if word == "women":
                return [
                    {
                        "wn_synset_id": "woman.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "adult female person",
                        "canonical_label": "woman",
                    }
                ]
            return []

        result = build_base_records(
            words=["people's", "children's", "men's", "women's", "today's"],
            snapshot_id="lexicon-20260314-possessive-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["child", "man", "people", "today", "woman"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["people's"].canonical_form, "people")
        self.assertEqual(variants["people's"].decision, "collapse_to_canonical")
        self.assertEqual(variants["children's"].canonical_form, "child")
        self.assertEqual(variants["children's"].decision, "collapse_to_canonical")
        self.assertEqual(variants["men's"].canonical_form, "man")
        self.assertEqual(variants["men's"].decision, "collapse_to_canonical")
        self.assertEqual(variants["women's"].canonical_form, "woman")
        self.assertEqual(variants["women's"].decision, "collapse_to_canonical")
        self.assertEqual(variants["today's"].canonical_form, "today")
        self.assertEqual(variants["today's"].decision, "collapse_to_canonical")

    def test_build_base_records_keeps_true_apostrophe_s_contractions_separate(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "it's": 120,
                "it": 20,
                "that's": 130,
                "that": 30,
                "who's": 140,
                "who": 40,
                "let's": 150,
                "let": 50,
                "one's": 160,
                "one": 60,
            }.get(word, 999_999)

        def sense_provider(word: str):
            return []

        result = build_base_records(
            words=["it's", "that's", "who's", "let's", "one's"],
            snapshot_id="lexicon-20260314-possessive-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["it's", "let's", "one's", "that's", "who's"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        for surface_form in ("it's", "that's", "who's", "let's", "one's"):
            self.assertEqual(variants[surface_form].decision, "keep_separate")
            self.assertEqual(variants[surface_form].canonical_form, surface_form)

    def test_build_base_records_collapses_possessive_eponyms_without_wordnet_surface_senses(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "alzheimer's": 50,
                "alzheimer": 200,
                "valentine's": 60,
                "valentine": 250,
            }.get(word, 999_999)

        def sense_provider(word: str):
            return []

        result = build_base_records(
            words=["alzheimer's", "valentine's"],
            snapshot_id="lexicon-20260314-possessive-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["alzheimer", "valentine"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["alzheimer's"].canonical_form, "alzheimer")
        self.assertEqual(variants["alzheimer's"].decision, "collapse_to_canonical")
        self.assertEqual(variants["valentine's"].canonical_form, "valentine")
        self.assertEqual(variants["valentine's"].decision, "collapse_to_canonical")

    def test_build_base_records_collapses_wordnet_backed_possessive_surface_forms(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "levi's": 80,
                "levi": 120,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "levi's":
                return [
                    {
                        "wn_synset_id": "levi's.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a denim clothing brand",
                        "canonical_label": "Levi's",
                    }
                ]
            if word == "levi":
                return [
                    {
                        "wn_synset_id": "levi.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a proper-name base form",
                        "canonical_label": "Levi",
                    }
                ]
            return []

        result = build_base_records(
            words=["levi's"],
            snapshot_id="lexicon-20260314-possessive-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["levi's"])
        variant = result.canonical_variants[0]
        self.assertEqual(variant.surface_form, "levi's")
        self.assertEqual(variant.canonical_form, "levi's")
        self.assertEqual(variant.decision, "keep_separate")

    def test_build_base_records_keeps_name_like_s_ending_surface_form_separate_via_anomaly_override(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "james": 80,
                "jam": 120,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "james":
                return [
                    {
                        "wn_synset_id": "james.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a male given name",
                        "canonical_label": "James",
                    }
                ]
            return []

        with patch(
            "tools.lexicon.canonical_forms._load_canonical_anomaly_overrides",
            return_value={
                "force_keep_separate": {
                    "james": {"reason": "given_name_like"}
                },
                "force_collapse_to_canonical": {},
            },
            create=True,
        ):
            result = build_base_records(
                words=["james"],
                snapshot_id="lexicon-20260314-name-like-s-ending-hardening",
                created_at="2026-03-14T00:00:00Z",
                rank_provider=rank_provider,
                sense_provider=sense_provider,
            )

        self.assertEqual([record.lemma for record in result.lexemes], ["james"])
        variant = result.canonical_variants[0]
        self.assertEqual(variant.surface_form, "james")
        self.assertEqual(variant.canonical_form, "james")
        self.assertEqual(variant.decision, "keep_separate")

    def test_build_base_records_keeps_lexicalized_irregular_participles_linked(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "lost": 80,
                "lose": 40,
                "broken": 85,
                "break": 45,
                "taken": 90,
                "take": 50,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "lost":
                return [
                    {
                        "wn_synset_id": "lost.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "unable to find the way",
                        "canonical_label": "lost",
                    },
                    {
                        "wn_synset_id": "lose.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to fail to keep or maintain",
                        "canonical_label": "lose",
                    },
                ]
            if word == "broken":
                return [
                    {
                        "wn_synset_id": "broken.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "damaged or not working",
                        "canonical_label": "broken",
                    },
                    {
                        "wn_synset_id": "break.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to separate into pieces",
                        "canonical_label": "break",
                    },
                ]
            if word == "taken":
                return [
                    {
                        "wn_synset_id": "taken.a.01",
                        "part_of_speech": "adjective",
                        "canonical_gloss": "already occupied or committed",
                        "canonical_label": "taken",
                    },
                    {
                        "wn_synset_id": "take.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "to get into one's possession",
                        "canonical_label": "take",
                    },
                ]
            return []

        result = build_base_records(
            words=["lost", "broken", "taken"],
            snapshot_id="lexicon-20260314-irregular-verb-hardening",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(sorted(record.lemma for record in result.lexemes), ["broken", "lost", "taken"])
        variants = {record.surface_form: record for record in result.canonical_variants}
        self.assertEqual(variants["lost"].linked_canonical_form, "lose")
        self.assertEqual(variants["broken"].linked_canonical_form, "break")
        self.assertEqual(variants["taken"].linked_canonical_form, "take")
        self.assertTrue(all(variant.decision == "keep_both_linked" for variant in variants.values()))


if __name__ == "__main__":
    unittest.main()
