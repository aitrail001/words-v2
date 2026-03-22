import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon.benchmark_selection import load_benchmark_words, run_selection_benchmark


EXPECTED_TUNING_WORDS = [
    "right",
    "direct",
    "common",
    "fine",
    "fair",
    "plain",
    "check",
    "charge",
    "scale",
    "break",
]

EXPECTED_HOLDOUT_WORDS = [
    "bank",
    "case",
    "point",
    "change",
    "turn",
    "pass",
    "mean",
    "sound",
    "order",
    "issue",
    "mark",
    "line",
    "match",
    "record",
    "spring",
    "state",
    "object",
    "file",
    "face",
    "present",
]


class BenchmarkSelectionTests(unittest.TestCase):
    def test_load_benchmark_words_for_known_splits(self) -> None:
        self.assertEqual(load_benchmark_words("tuning"), EXPECTED_TUNING_WORDS)
        self.assertEqual(load_benchmark_words("holdout"), EXPECTED_HOLDOUT_WORDS)

    def test_benchmark_word_lists_are_disjoint_and_unique(self) -> None:
        tuning_words = load_benchmark_words("tuning")
        holdout_words = load_benchmark_words("holdout")

        self.assertEqual(len(tuning_words), len(set(tuning_words)))
        self.assertEqual(len(holdout_words), len(set(holdout_words)))
        self.assertTrue(set(tuning_words).isdisjoint(set(holdout_words)))
        self.assertEqual(len(holdout_words), 20)

    def test_run_selection_benchmark_writes_deterministic_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"
            result = run_selection_benchmark(
                output_dir,
                datasets=["tuning"],
                max_senses=4,
                rank_provider=lambda word: 1,
                sense_provider=lambda lemma: [
                    {
                        "query_lemma": lemma,
                        "wn_synset_id": f"{lemma}.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": f"general meaning for {lemma}",
                        "canonical_label": lemma,
                        "lemma_count": 10,
                    }
                ],
            )

            self.assertTrue(result.summary_path.exists())
            self.assertEqual(result.payload["output_dir"], str(output_dir))
            self.assertEqual(len(result.payload["datasets"]), 1)
            dataset = result.payload["datasets"][0]
            self.assertEqual(dataset["dataset"], "tuning")
            self.assertEqual(dataset["words"], EXPECTED_TUNING_WORDS)
            self.assertEqual(dataset["lexeme_count"], len(EXPECTED_TUNING_WORDS))
            self.assertEqual(dataset["sense_count"], len(EXPECTED_TUNING_WORDS))
            self.assertEqual(dataset["rerank_runs"], [])
            snapshot_dir = Path(dataset["snapshot_dir"])
            self.assertTrue((snapshot_dir / "lexemes.jsonl").exists())

    def test_run_selection_benchmark_runs_requested_rerank_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"

            def fake_run_rerank(snapshot_dir, **kwargs):
                output_path = Path(kwargs["output_path"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("", encoding="utf-8")
                return type(
                    "FakeRerankRunResult",
                    (),
                    {
                        "output_path": output_path,
                        "rows": [{"lexeme_id": "lx_run", "candidate_source": kwargs["candidate_source"]}],
                    },
                )()

            with patch("tools.lexicon.benchmark_selection.run_rerank", side_effect=fake_run_rerank) as mocked_rerank, patch(
                "tools.lexicon.benchmark_selection.compare_selection_artifacts",
                return_value={
                    "compared_lexeme_count": 1,
                    "changed_lexeme_count": 1,
                    "changes": [],
                },
            ) as mocked_compare:
                result = run_selection_benchmark(
                    output_dir,
                    datasets=["holdout"],
                    max_senses=4,
                    with_rerank=True,
                    candidate_sources=["selected_only", "candidates", "full_wordnet"],
                    provider_mode="openai_compatible",
                    candidate_limit=8,
                    rank_provider=lambda word: 1,
                    sense_provider=lambda lemma: [
                        {
                            "query_lemma": lemma,
                            "wn_synset_id": f"{lemma}.n.01",
                            "part_of_speech": "noun",
                            "canonical_gloss": f"general meaning for {lemma}",
                            "canonical_label": lemma,
                            "lemma_count": 10,
                        }
                    ],
                )

            dataset = result.payload["datasets"][0]
            self.assertEqual(dataset["dataset"], "holdout")
            self.assertEqual(len(dataset["rerank_runs"]), 3)
            self.assertEqual(
                [item["candidate_source"] for item in dataset["rerank_runs"]],
                ["selected_only", "candidates", "full_wordnet"],
            )
            self.assertEqual(mocked_rerank.call_count, 3)
            self.assertEqual(mocked_compare.call_count, 3)


if __name__ == "__main__":
    unittest.main()
