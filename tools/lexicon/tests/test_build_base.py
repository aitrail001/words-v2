import tempfile
import unittest
from pathlib import Path

from tools.lexicon.build_base import build_base_records, normalize_seed_words, write_base_snapshot
from tools.lexicon.ids import make_concept_id


class BuildBaseTests(unittest.TestCase):
    def test_normalize_seed_words_lowercases_strips_and_deduplicates(self) -> None:
        words = normalize_seed_words([" Run ", "run", "SET", "", " set ", "lead"])

        self.assertEqual(words, ["run", "set", "lead"])

    def test_normalize_seed_words_filters_obvious_junk_tokens(self) -> None:
        words = normalize_seed_words(
            [" Run ", "can't", "co-op", "foo bar", "123", "a1", "___", "e-mail", "a's", "n't"]
        )

        self.assertEqual(words, ["run", "can't", "co-op", "e-mail"])

    def test_normalize_seed_words_applies_surface_form_overrides(self) -> None:
        words = normalize_seed_words(["gov't", "int'l", "ya'll", "GOV'T", "ya'll"])

        self.assertEqual(words, ["government", "international", "y'all"])

    def test_normalize_seed_words_drops_curated_noise_surface_forms(self) -> None:
        words = normalize_seed_words(
            ["childrens", "womens", "dont", "atleast", "bl", "seperate", "longterm", "lyin", "actual"]
        )

        self.assertEqual(words, ["actual"])

    def test_build_word_inventory_normalizes_filters_and_bounds_top_words(self) -> None:
        from tools.lexicon.build_base import build_word_inventory

        def inventory_provider(limit: int):
            self.assertEqual(limit, 5)
            return ["The", "and", "gov't", "foo bar", "a's", "can't", "THE"]

        words = build_word_inventory(limit=5, inventory_provider=inventory_provider)

        self.assertEqual(words, ["the", "and", "government", "can't"])

    def test_build_base_records_builds_linked_records_from_providers(self) -> None:
        def rank_provider(word: str) -> int:
            return {"run": 5}[word]

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "an act of running",
                    "canonical_label": "run",
                },
            ]

        result = build_base_records(
            words=["run"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["run"])
        self.assertEqual(result.lexemes[0].entry_type, "word")
        self.assertEqual(result.lexemes[0].entry_id, "lx_run")
        self.assertEqual(result.lexemes[0].normalized_form, "run")
        self.assertEqual(result.lexemes[0].source_provenance, [{"source": "wordfreq", "role": "frequency_rank"}, {"source": "wordnet", "role": "sense_grounding"}])
        self.assertEqual(result.lexemes[0].wordfreq_rank, 5)
        self.assertEqual([record.sense_id for record in result.senses], ["sn_lx_run_1", "sn_lx_run_2"])
        self.assertEqual(result.senses[0].wn_synset_id, "run.v.01")
        self.assertEqual(
            [record.concept_id for record in result.concepts],
            [make_concept_id("run.v.01"), make_concept_id("run.n.01")],
        )

    def test_build_base_records_limits_selected_senses(self) -> None:
        def rank_provider(word: str) -> int:
            return 10

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": f"set.n.0{idx}",
                    "part_of_speech": "noun",
                    "canonical_gloss": f"gloss {idx}",
                    "canonical_label": "set",
                }
                for idx in range(1, 7)
            ]

        result = build_base_records(
            words=["set"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        self.assertEqual(len(result.senses), 4)
        self.assertTrue(all(record.is_high_polysemy for record in result.senses))

    def test_build_base_records_dedupes_selected_senses_with_same_pos_and_gloss(self) -> None:
        def rank_provider(word: str) -> int:
            return 10

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "occasional.s.01",
                    "part_of_speech": "adjective",
                    "canonical_gloss": "occurring from time to time",
                    "canonical_label": "occasional",
                },
                {
                    "wn_synset_id": "occasional.s.02",
                    "part_of_speech": "adjective",
                    "canonical_gloss": "occurring from time to time",
                    "canonical_label": "occasional",
                },
            ]

        result = build_base_records(
            words=["occasional"],
            snapshot_id="lexicon-20260314-wordnet-wordfreq",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(len(result.senses), 1)
        self.assertEqual(result.senses[0].canonical_gloss, "occurring from time to time")

    def test_build_base_records_falls_back_when_no_canonical_senses_exist(self) -> None:
        def rank_provider(word: str) -> int:
            return 200

        def sense_provider(word: str):
            return []

        result = build_base_records(
            words=["algorithm"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(len(result.lexemes), 1)
        self.assertEqual(len(result.senses), 1)
        self.assertEqual(result.senses[0].wn_synset_id, None)
        self.assertEqual(result.senses[0].part_of_speech, "noun")
        self.assertEqual(result.concepts, [])
        self.assertFalse(result.lexemes[0].is_wordnet_backed)

    def test_build_base_records_skips_existing_published_canonical_words(self) -> None:
        def rank_provider(word: str) -> int:
            return {"things": 10, "thing": 10, "run": 20}[word]

        def sense_provider(word: str):
            canonical_label = "thing" if word == "things" else word
            synset_label = canonical_label
            return [
                {
                    "wn_synset_id": f"{synset_label}.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": f"gloss for {canonical_label}",
                    "canonical_label": canonical_label,
                }
            ]

        seen_lookup_inputs: list[list[str]] = []

        def existing_lookup(words: list[str]) -> set[str]:
            seen_lookup_inputs.append(list(words))
            return {"thing"}

        result = build_base_records(
            words=["things", "run"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            existing_canonical_words_lookup=existing_lookup,
        )

        self.assertEqual(seen_lookup_inputs, [["thing", "run"]])
        self.assertEqual([record.lemma for record in result.lexemes], ["run"])
        self.assertEqual(result.skipped_existing_canonical_words, ["thing"])
        self.assertEqual([record.canonical_form for record in result.canonical_entries], ["thing", "run"])
        skipped_status = next(record for record in result.generation_status if record.canonical_form == "thing")
        self.assertFalse(skipped_status.base_built)
        self.assertTrue(skipped_status.published)
        self.assertEqual(skipped_status.last_source_reference, "db_existing_skip")

    def test_build_base_records_marks_linked_lexicalized_variants_in_lexeme_rows(self) -> None:
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
            snapshot_id="lexicon-20260314-wordnet-wordfreq",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["meeting"])
        self.assertTrue(result.lexemes[0].is_variant_with_distinct_meanings)
        self.assertEqual(result.lexemes[0].variant_base_form, "meet")
        self.assertEqual(result.lexemes[0].variant_relationship, "lexicalized_form")

    def test_build_base_records_applies_entity_categories_from_dataset(self) -> None:
        def rank_provider(word: str) -> int:
            return {"kinshasa": 39386}[word]

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "kinshasa.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "the capital city of the Democratic Republic of the Congo",
                    "canonical_label": "Kinshasa",
                }
            ]

        result = build_base_records(
            words=["kinshasa"],
            snapshot_id="lexicon-20260314-wordnet-wordfreq",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(result.lexemes[0].entity_category, "place")
        self.assertIn(
            {"source": "entity_categories", "role": "entity_category", "category": "place", "reason": "place_name"},
            result.lexemes[0].source_provenance,
        )

    def test_build_base_records_excludes_tail_canonical_forms_only_when_requested(self) -> None:
        def rank_provider(word: str) -> int:
            return {"json": 39378, "merlot": 39424}[word]

        def sense_provider(word: str):
            if word == "json":
                return []
            return [
                {
                    "wn_synset_id": "merlot.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a dark red wine grape and wine",
                    "canonical_label": "merlot",
                }
            ]

        result = build_base_records(
            words=["json", "merlot"],
            snapshot_id="lexicon-20260314-wordnet-wordfreq",
            created_at="2026-03-14T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            excluded_canonical_words={"json"},
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["merlot"])
        self.assertEqual(result.excluded_tail_canonical_words, ["json"])
        self.assertEqual([record.surface_form for record in result.canonical_variants], ["merlot"])

    def test_build_base_records_only_calls_sense_provider_once_per_word(self) -> None:
        calls = []

        def rank_provider(word: str) -> int:
            return 10

        def sense_provider(word: str):
            calls.append(word)
            return [
                {
                    "wn_synset_id": "set.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a group of things",
                    "canonical_label": "set",
                }
            ]

        build_base_records(
            words=["set"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(calls, ["set"])

    def test_write_base_snapshot_writes_jsonl_files(self) -> None:
        def rank_provider(word: str) -> int:
            return {"run": 5}[word]

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "canonical_label": "run",
                }
            ]

        result = build_base_records(
            words=["run"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_base_snapshot(Path(tmpdir), result)

            self.assertTrue(paths["lexemes"].exists())
            self.assertTrue(paths["senses"].exists())
            self.assertTrue(paths["concepts"].exists())
            self.assertIn('"lemma": "run"', paths["lexemes"].read_text())
            self.assertIn('"wn_synset_id": "run.v.01"', paths["senses"].read_text())

    def test_build_base_records_prioritizes_general_verbs_for_polysemous_words(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "run.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a score in baseball or cricket",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.n.02",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a continuous period of performances in a theater",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.v.02",
                    "part_of_speech": "verb",
                    "canonical_gloss": "operate or function",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.v.03",
                    "part_of_speech": "verb",
                    "canonical_gloss": "manage or conduct a business or activity",
                    "canonical_label": "run",
                },
            ]

        result = build_base_records(
            words=["run"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_pos = [record.part_of_speech for record in result.senses]
        self.assertIn("verb", selected_pos)
        self.assertEqual(result.senses[0].part_of_speech, "verb")

    def test_build_base_records_allows_competitive_nouns_to_surface(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "set.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a group of things that belong together",
                    "canonical_label": "set",
                },
                {
                    "wn_synset_id": "set.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "put something in a particular place",
                    "canonical_label": "set",
                },
                {
                    "wn_synset_id": "set.v.02",
                    "part_of_speech": "verb",
                    "canonical_gloss": "make ready or prepare something",
                    "canonical_label": "set",
                },
                {
                    "wn_synset_id": "set.n.02",
                    "part_of_speech": "noun",
                    "canonical_gloss": "the scenery used for a play or film",
                    "canonical_label": "set",
                },
            ]

        result = build_base_records(
            words=["set"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertIn("set.n.01", selected_ids)
        self.assertIn("set.v.01", selected_ids)

    def test_build_base_records_suppresses_specialized_nouns_in_top_four(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": "run.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a score in baseball",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.n.02",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a test run of software or machinery",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.v.02",
                    "part_of_speech": "verb",
                    "canonical_gloss": "operate or function correctly",
                    "canonical_label": "run",
                },
                {
                    "wn_synset_id": "run.n.03",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a continuous period of luck or success",
                    "canonical_label": "run",
                },
            ]

        result = build_base_records(
            words=["run"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertNotIn("run.n.01", selected_ids)
        self.assertIn("run.v.01", selected_ids)
        self.assertIn("run.v.02", selected_ids)

    def test_build_base_records_expands_to_six_only_when_many_senses_are_strong(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "alpha.v.01", "part_of_speech": "verb", "canonical_gloss": "move and operate in a general everyday way", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.v.02", "part_of_speech": "verb", "canonical_gloss": "put and manage a person or activity", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.v.03", "part_of_speech": "verb", "canonical_gloss": "guide and prepare a group for an event", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.n.01", "part_of_speech": "noun", "canonical_gloss": "a group or collection that belongs together", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.a.01", "part_of_speech": "adjective", "canonical_gloss": "most important or principal in a general everyday activity or event", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.r.01", "part_of_speech": "adverb", "canonical_gloss": "in the first position in a general race or everyday event or activity", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.n.02", "part_of_speech": "noun", "canonical_gloss": "the score in baseball", "canonical_label": "alpha"},
                {"wn_synset_id": "alpha.n.03", "part_of_speech": "noun", "canonical_gloss": "a toxic metallic element", "canonical_label": "alpha"},
            ]

        result = build_base_records(
            words=["alpha"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=8,
        )

        self.assertEqual(len(result.senses), 6)

    def test_build_base_records_does_not_force_low_value_nouns_into_top_four(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "lead.v.01", "part_of_speech": "verb", "canonical_gloss": "guide a person or group", "canonical_label": "lead"},
                {"wn_synset_id": "lead.v.02", "part_of_speech": "verb", "canonical_gloss": "be in charge of a team or activity", "canonical_label": "lead"},
                {"wn_synset_id": "lead.v.03", "part_of_speech": "verb", "canonical_gloss": "cause something to happen or result", "canonical_label": "lead"},
                {"wn_synset_id": "lead.v.04", "part_of_speech": "verb", "canonical_gloss": "take somebody somewhere", "canonical_label": "lead"},
                {"wn_synset_id": "lead.n.01", "part_of_speech": "noun", "canonical_gloss": "the angle between the direction a gun is aimed and the position of a moving target", "canonical_label": "lead"},
            ]

        result = build_base_records(
            words=["lead"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertNotIn("lead.n.01", selected_ids)

    def test_build_base_records_uses_lemma_count_to_surface_high_value_nouns(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "project.n.01", "part_of_speech": "noun", "canonical_gloss": "any piece of work that is undertaken or attempted", "canonical_label": "project", "lemma_count": 23},
                {"wn_synset_id": "project.n.02", "part_of_speech": "noun", "canonical_gloss": "a planned undertaking", "canonical_label": "project", "lemma_count": 1},
                {"wn_synset_id": "project.v.01", "part_of_speech": "verb", "canonical_gloss": "make or work out a plan for; devise", "canonical_label": "project", "lemma_count": 1},
                {"wn_synset_id": "project.v.02", "part_of_speech": "verb", "canonical_gloss": "put or send forth", "canonical_label": "project", "lemma_count": 1},
                {"wn_synset_id": "project.v.03", "part_of_speech": "verb", "canonical_gloss": "communicate vividly", "canonical_label": "project", "lemma_count": 7},
                {"wn_synset_id": "project.v.04", "part_of_speech": "verb", "canonical_gloss": "extend out or project in space", "canonical_label": "project", "lemma_count": 6},
            ]

        result = build_base_records(
            words=["project"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertIn("project.n.01", selected_ids)
        self.assertIn(result.senses[1].wn_synset_id, ["project.n.01", "project.v.01"])
        self.assertIn("project.n.01", [result.senses[0].wn_synset_id, result.senses[1].wn_synset_id])

    def test_build_base_records_uses_lemma_count_without_promoting_specialized_senses(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "light.n.01", "part_of_speech": "noun", "canonical_gloss": "physics electromagnetic radiation that can produce a visual sensation", "canonical_label": "light", "lemma_count": 46},
                {"wn_synset_id": "light.n.02", "part_of_speech": "noun", "canonical_gloss": "any device serving as a source of illumination", "canonical_label": "light", "lemma_count": 23},
                {"wn_synset_id": "light.v.01", "part_of_speech": "verb", "canonical_gloss": "make lighter or brighter", "canonical_label": "light", "lemma_count": 12},
                {"wn_synset_id": "light.v.02", "part_of_speech": "verb", "canonical_gloss": "begin to smoke", "canonical_label": "light", "lemma_count": 10},
                {"wn_synset_id": "light.a.01", "part_of_speech": "adjective", "canonical_gloss": "of comparatively little physical weight or density", "canonical_label": "light", "lemma_count": 14},
            ]

        result = build_base_records(
            words=["light"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertIn("light.n.02", selected_ids)
        self.assertNotIn("light.n.01", selected_ids[:2])
        self.assertIn("light.a.01", selected_ids)

    def test_build_base_records_expands_to_eight_when_eight_competitive_senses_exist(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "broad.v.01", "part_of_speech": "verb", "canonical_gloss": "move and operate in a general everyday way", "canonical_label": "broad", "lemma_count": 24},
                {"wn_synset_id": "broad.v.02", "part_of_speech": "verb", "canonical_gloss": "put and manage a person or activity", "canonical_label": "broad", "lemma_count": 22},
                {"wn_synset_id": "broad.v.03", "part_of_speech": "verb", "canonical_gloss": "guide and prepare a group for an event", "canonical_label": "broad", "lemma_count": 20},
                {"wn_synset_id": "broad.v.04", "part_of_speech": "verb", "canonical_gloss": "make and use something in a general everyday way", "canonical_label": "broad", "lemma_count": 18},
                {"wn_synset_id": "broad.n.01", "part_of_speech": "noun", "canonical_gloss": "a group or collection of work items used together", "canonical_label": "broad", "lemma_count": 26},
                {"wn_synset_id": "broad.n.02", "part_of_speech": "noun", "canonical_gloss": "a device or source of information used in everyday activity", "canonical_label": "broad", "lemma_count": 23},
                {"wn_synset_id": "broad.a.01", "part_of_speech": "adjective", "canonical_gloss": "important and general in everyday use or activity", "canonical_label": "broad", "lemma_count": 21},
                {"wn_synset_id": "broad.a.02", "part_of_speech": "adjective", "canonical_gloss": "ready for general use in an important event or activity", "canonical_label": "broad", "lemma_count": 19},
            ]

        result = build_base_records(
            words=["broad"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=8,
        )

        self.assertEqual(len(result.senses), 8)

    def test_build_base_records_surfaces_high_value_adjectives_for_mixed_pos_words(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "right.n.01", "part_of_speech": "noun", "canonical_gloss": "location near or direction toward the right side", "canonical_label": "right", "lemma_count": 22},
                {"wn_synset_id": "right.v.01", "part_of_speech": "verb", "canonical_gloss": "put in or restore to an upright position", "canonical_label": "right", "lemma_count": 10},
                {"wn_synset_id": "right.v.02", "part_of_speech": "verb", "canonical_gloss": "make right or correct", "canonical_label": "right", "lemma_count": 8},
                {"wn_synset_id": "right.n.02", "part_of_speech": "noun", "canonical_gloss": "an abstract idea of what is due by law or tradition", "canonical_label": "right", "lemma_count": 18},
                {"wn_synset_id": "right.a.01", "part_of_speech": "adjective", "canonical_gloss": "free from error; especially conforming to fact or truth", "canonical_label": "right", "lemma_count": 28},
                {"wn_synset_id": "right.r.01", "part_of_speech": "adverb", "canonical_gloss": "precisely, exactly, or directly", "canonical_label": "right", "lemma_count": 14},
            ]

        result = build_base_records(
            words=["right"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertGreaterEqual(len(result.senses), 5)
        self.assertIn("right.a.01", selected_ids)
        self.assertIn("right.n.01", selected_ids)
        self.assertTrue(any(record.part_of_speech == "verb" for record in result.senses))

    def test_build_base_records_can_expand_to_include_viable_adjective_within_ceiling(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "direct.v.01", "part_of_speech": "verb", "canonical_gloss": "command with authority", "canonical_label": "direct", "lemma_count": 20},
                {"wn_synset_id": "direct.v.02", "part_of_speech": "verb", "canonical_gloss": "guide actors in a performance", "canonical_label": "direct", "lemma_count": 14},
                {"wn_synset_id": "direct.v.03", "part_of_speech": "verb", "canonical_gloss": "point or cause to move toward a place", "canonical_label": "direct", "lemma_count": 16},
                {"wn_synset_id": "direct.v.04", "part_of_speech": "verb", "canonical_gloss": "address questions or remarks to", "canonical_label": "direct", "lemma_count": 10},
                {"wn_synset_id": "direct.a.01", "part_of_speech": "adjective", "canonical_gloss": "straight and without deviation", "canonical_label": "direct", "lemma_count": 24},
                {"wn_synset_id": "direct.r.01", "part_of_speech": "adverb", "canonical_gloss": "without changing direction or stopping", "canonical_label": "direct", "lemma_count": 8},
            ]

        result = build_base_records(
            words=["direct"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        self.assertEqual(len(result.senses), 6)
        self.assertTrue(any(record.part_of_speech == "adjective" for record in result.senses))

    def test_build_base_records_keeps_break_noun_verb_only(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "break.v.01", "part_of_speech": "verb", "canonical_gloss": "separate into pieces", "canonical_label": "break", "lemma_count": 24},
                {"wn_synset_id": "break.v.02", "part_of_speech": "verb", "canonical_gloss": "interrupt a continued activity", "canonical_label": "break", "lemma_count": 16},
                {"wn_synset_id": "break.n.01", "part_of_speech": "noun", "canonical_gloss": "a pause in an activity", "canonical_label": "break", "lemma_count": 21},
                {"wn_synset_id": "break.n.02", "part_of_speech": "noun", "canonical_gloss": "an abrupt interruption", "canonical_label": "break", "lemma_count": 12},
            ]

        result = build_base_records(
            words=["break"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        self.assertTrue(all(record.part_of_speech in {"noun", "verb"} for record in result.senses))

    def test_build_base_records_prefers_core_break_verb_over_obedience_sense(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "break.v.core", "part_of_speech": "verb", "canonical_gloss": "separate into pieces as a result of a blow, shock, or strain", "canonical_label": "break", "lemma_count": 24},
                {"wn_synset_id": "break.v.pause", "part_of_speech": "verb", "canonical_gloss": "interrupt a continued activity", "canonical_label": "break", "lemma_count": 16},
                {"wn_synset_id": "break.v.obedience", "part_of_speech": "verb", "canonical_gloss": "make submissive, obedient, or useful", "canonical_label": "break", "lemma_count": 27},
                {"wn_synset_id": "break.n.pause", "part_of_speech": "noun", "canonical_gloss": "a pause in an activity during which refreshments may be served", "canonical_label": "break", "lemma_count": 21},
                {"wn_synset_id": "break.n.interrupt", "part_of_speech": "noun", "canonical_gloss": "an abrupt interruption", "canonical_label": "break", "lemma_count": 12},
                {"wn_synset_id": "break.n.crack", "part_of_speech": "noun", "canonical_gloss": "a crack or opening made by breaking something", "canonical_label": "break", "lemma_count": 7},
            ]

        result = build_base_records(
            words=["break"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertTrue("break.v.obedience" not in selected_ids or selected_ids.index("break.v.core") < selected_ids.index("break.v.obedience"))

    def test_build_base_records_prefers_general_open_adjective_over_body_part_only_or_specialized_senses(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"wn_synset_id": "open.v.start", "part_of_speech": "verb", "canonical_gloss": "cause to open or to become open", "canonical_label": "open", "lemma_count": 30},
                {"wn_synset_id": "open.a.general", "part_of_speech": "adjective", "canonical_gloss": "not closed or shut", "canonical_label": "open", "lemma_count": 28},
                {"wn_synset_id": "open.a.body", "part_of_speech": "adjective", "canonical_gloss": "with mouth or eyes open", "canonical_label": "open", "lemma_count": 22},
                {"wn_synset_id": "open.a.frank", "part_of_speech": "adjective", "canonical_gloss": "willing to consider new ideas", "canonical_label": "open", "lemma_count": 16},
                {"wn_synset_id": "open.n.tournament", "part_of_speech": "noun", "canonical_gloss": "a tournament in which both professionals and amateurs may play", "canonical_label": "open", "lemma_count": 9},
            ]

        result = build_base_records(
            words=["open"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertIn("open.a.general", selected_ids)
        self.assertNotIn("open.a.body", selected_ids[:3])
        self.assertNotIn("open.n.tournament", selected_ids[:4])

    def test_build_base_records_keeps_narrow_words_at_four_even_with_eight_ceiling(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {
                    "wn_synset_id": f"play.n.0{idx}",
                    "part_of_speech": "noun",
                    "canonical_gloss": f"general gloss {idx}",
                    "canonical_label": "play",
                }
                for idx in range(1, 7)
            ]

        result = build_base_records(
            words=["play"],
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            created_at="2026-03-07T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=8,
        )

        self.assertEqual(len(result.senses), 4)

    def test_build_base_records_demotes_alias_like_direct_synsets(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "direct", "wn_synset_id": "calculate.v.05", "part_of_speech": "verb", "canonical_gloss": "specifically design a product, event, or activity for a certain public", "canonical_label": "calculate", "lemma_count": 18},
                {"query_lemma": "direct", "wn_synset_id": "target.v.01", "part_of_speech": "verb", "canonical_gloss": "intend something to move towards a certain goal", "canonical_label": "target", "lemma_count": 14},
                {"query_lemma": "direct", "wn_synset_id": "direct.a.03", "part_of_speech": "adjective", "canonical_gloss": "straightforward in means or manner or behavior or language or action", "canonical_label": "direct", "lemma_count": 24},
                {"query_lemma": "direct", "wn_synset_id": "direct.v.09", "part_of_speech": "verb", "canonical_gloss": "give directions to or point somebody into a certain direction", "canonical_label": "direct", "lemma_count": 22},
                {"query_lemma": "direct", "wn_synset_id": "direct.v.01", "part_of_speech": "verb", "canonical_gloss": "command with authority", "canonical_label": "direct", "lemma_count": 10},
            ]

        result = build_base_records(
            words=["direct"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=6,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("direct.a.03"), selected_ids.index("calculate.v.05"))
        self.assertTrue("target.v.01" not in selected_ids or selected_ids.index("direct.v.09") < selected_ids.index("target.v.01"))

    def test_build_base_records_prefers_everyday_common_adjective_over_land_noun(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "common", "wn_synset_id": "common.n.01", "part_of_speech": "noun", "canonical_gloss": "a piece of open land for recreational use in an urban area", "canonical_label": "common", "lemma_count": 18},
                {"query_lemma": "common", "wn_synset_id": "common.a.01", "part_of_speech": "adjective", "canonical_gloss": "belonging to or participated in by a community as a whole; public", "canonical_label": "common", "lemma_count": 24},
                {"query_lemma": "common", "wn_synset_id": "common.a.02", "part_of_speech": "adjective", "canonical_gloss": "having no special distinction or quality; widely known or commonly encountered", "canonical_label": "common", "lemma_count": 20},
                {"query_lemma": "common", "wn_synset_id": "common.a.03", "part_of_speech": "adjective", "canonical_gloss": "common to or shared by two or more parties", "canonical_label": "common", "lemma_count": 12},
            ]

        result = build_base_records(
            words=["common"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("common.a.01"), selected_ids.index("common.n.01"))

    def test_build_base_records_prefers_check_verify_over_crack_or_discipline_tails(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "check", "wn_synset_id": "check.v.01", "part_of_speech": "verb", "canonical_gloss": "examine so as to determine accuracy, quality, or condition", "canonical_label": "check", "lemma_count": 26},
                {"query_lemma": "check", "wn_synset_id": "check.n.01", "part_of_speech": "noun", "canonical_gloss": "a written order directing a bank to pay money", "canonical_label": "check", "lemma_count": 14},
                {"query_lemma": "check", "wn_synset_id": "discipline.v.01", "part_of_speech": "verb", "canonical_gloss": "make cracks or chinks in; check the surface of", "canonical_label": "discipline", "lemma_count": 18},
                {"query_lemma": "check", "wn_synset_id": "check.v.tail", "part_of_speech": "verb", "canonical_gloss": "slow the growth or development of", "canonical_label": "check", "lemma_count": 8},
            ]

        result = build_base_records(
            words=["check"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("check.v.01"), selected_ids.index("discipline.v.01"))
        self.assertLess(selected_ids.index("check.n.01"), selected_ids.index("discipline.v.01"))

    def test_build_base_records_surfaces_measurement_scale_noun(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "scale", "wn_synset_id": "scale.n.01", "part_of_speech": "noun", "canonical_gloss": "an ordered reference standard used to measure or compare magnitude", "canonical_label": "scale", "lemma_count": 18},
                {"query_lemma": "scale", "wn_synset_id": "scale.v.01", "part_of_speech": "verb", "canonical_gloss": "climb up by means of feet and hands", "canonical_label": "scale", "lemma_count": 20},
                {"query_lemma": "scale", "wn_synset_id": "scale.v.02", "part_of_speech": "verb", "canonical_gloss": "remove the scales from", "canonical_label": "scale", "lemma_count": 12},
                {"query_lemma": "scale", "wn_synset_id": "scale.v.03", "part_of_speech": "verb", "canonical_gloss": "measure by or as if by a scale", "canonical_label": "scale", "lemma_count": 10},
            ]

        result = build_base_records(
            words=["scale"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertIn("scale.n.01", selected_ids[:2])

    def test_build_base_records_prefers_practical_charge_senses_over_attack_cluster(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "charge", "wn_synset_id": "charge.v.attack", "part_of_speech": "verb", "canonical_gloss": "move quickly and violently in a rush or attack", "canonical_label": "charge", "lemma_count": 20},
                {"query_lemma": "charge", "wn_synset_id": "charge.v.price", "part_of_speech": "verb", "canonical_gloss": "demand payment", "canonical_label": "charge", "lemma_count": 18},
                {"query_lemma": "charge", "wn_synset_id": "charge.n.price", "part_of_speech": "noun", "canonical_gloss": "the price asked for goods or services", "canonical_label": "charge", "lemma_count": 16},
                {"query_lemma": "charge", "wn_synset_id": "charge.v.accuse", "part_of_speech": "verb", "canonical_gloss": "accuse formally of a crime", "canonical_label": "charge", "lemma_count": 14},
            ]

        result = build_base_records(
            words=["charge"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("charge.v.price"), selected_ids.index("charge.v.attack"))


    def test_build_base_records_surfaces_file_record_sense_over_legal_or_procession_tails(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "file", "wn_synset_id": "file.v.01", "part_of_speech": "verb", "canonical_gloss": "record in a public office or in a court of law", "canonical_label": "file", "lemma_count": 22},
                {"query_lemma": "file", "wn_synset_id": "file.n.01", "part_of_speech": "noun", "canonical_gloss": "a set of related records kept together", "canonical_label": "file", "lemma_count": 18},
                {"query_lemma": "file", "wn_synset_id": "file.n.02", "part_of_speech": "noun", "canonical_gloss": "a line of persons or things ranged one behind the other", "canonical_label": "file", "lemma_count": 12},
                {"query_lemma": "file", "wn_synset_id": "file.v.02", "part_of_speech": "verb", "canonical_gloss": "smooth with a file", "canonical_label": "file", "lemma_count": 10},
            ]

        result = build_base_records(
            words=["file"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("file.n.01"), selected_ids.index("file.v.01"))

    def test_build_base_records_demotes_sports_pass_tails_below_general_senses(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "pass", "wn_synset_id": "pass.n.03", "part_of_speech": "noun", "canonical_gloss": "a football play that involves one player throwing the ball to a teammate", "canonical_label": "pass", "lemma_count": 18},
                {"query_lemma": "pass", "wn_synset_id": "pass.n.15", "part_of_speech": "noun", "canonical_gloss": "the sports act of throwing the ball to another member of your team", "canonical_label": "pass", "lemma_count": 14},
                {"query_lemma": "pass", "wn_synset_id": "pass.v.01", "part_of_speech": "verb", "canonical_gloss": "go across or through", "canonical_label": "pass", "lemma_count": 20},
                {"query_lemma": "pass", "wn_synset_id": "pass.v.14", "part_of_speech": "verb", "canonical_gloss": "go successfully through a test or a selection process", "canonical_label": "pass", "lemma_count": 16},
            ]

        result = build_base_records(
            words=["pass"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("pass.v.01"), selected_ids.index("pass.n.03"))
        self.assertLess(selected_ids.index("pass.v.14"), selected_ids.index("pass.n.15"))

    def test_build_base_records_demotes_point_geometry_and_diacritic_tails(self) -> None:
        def rank_provider(word: str) -> int:
            return 5

        def sense_provider(word: str):
            return [
                {"query_lemma": "point", "wn_synset_id": "point.n.01", "part_of_speech": "noun", "canonical_gloss": "a geometric element that has position but no extension", "canonical_label": "point", "lemma_count": 18},
                {"query_lemma": "point", "wn_synset_id": "point.v.02", "part_of_speech": "verb", "canonical_gloss": "indicate a place, direction, person, or thing", "canonical_label": "point", "lemma_count": 20},
                {"query_lemma": "point", "wn_synset_id": "point.n.02", "part_of_speech": "noun", "canonical_gloss": "the precise location of something", "canonical_label": "point", "lemma_count": 16},
                {"query_lemma": "point", "wn_synset_id": "point.v.07", "part_of_speech": "verb", "canonical_gloss": "mark Hebrew words with diacritics", "canonical_label": "point", "lemma_count": 10},
            ]

        result = build_base_records(
            words=["point"],
            snapshot_id="lexicon-20260308-wordnet-wordfreq",
            created_at="2026-03-08T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=4,
        )

        selected_ids = [record.wn_synset_id for record in result.senses]
        self.assertLess(selected_ids.index("point.v.02"), selected_ids.index("point.v.07"))
        self.assertLess(selected_ids.index("point.n.02"), selected_ids.index("point.n.01"))



if __name__ == "__main__":
    unittest.main()
