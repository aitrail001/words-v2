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


if __name__ == "__main__":
    unittest.main()
