import unittest

from tools.lexicon.build_base import build_base_records


class CanonicalFormsTests(unittest.TestCase):
    def test_build_base_records_collapses_plural_surface_form_to_canonical_lemma(self) -> None:
        def rank_provider(word: str) -> int:
            return {
                "things": 120,
                "thing": 40,
            }.get(word, 999_999)

        def sense_provider(word: str):
            if word == "things":
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


if __name__ == "__main__":
    unittest.main()
