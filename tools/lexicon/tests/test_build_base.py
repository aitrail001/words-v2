import tempfile
import unittest
from pathlib import Path

from tools.lexicon.build_base import build_base_records, normalize_seed_words, write_base_snapshot
from tools.lexicon.ids import make_concept_id


class BuildBaseTests(unittest.TestCase):
    def test_normalize_seed_words_lowercases_strips_and_deduplicates(self) -> None:
        words = normalize_seed_words([" Run ", "run", "SET", "", " set ", "lead"])

        self.assertEqual(words, ["run", "set", "lead"])

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


if __name__ == "__main__":
    unittest.main()
