import tempfile
import unittest
from pathlib import Path

from tools.lexicon.enrichment_benchmark import (
    load_enrichment_benchmark_metadata,
    load_enrichment_benchmark_words,
    run_enrichment_benchmark,
)


class EnrichmentBenchmarkTests(unittest.TestCase):
    def test_load_enrichment_benchmark_words(self) -> None:
        words = load_enrichment_benchmark_words("default")

        self.assertIn("building", words)
        self.assertIn("kinshasa", words)
        self.assertIn("break", words)
        self.assertEqual(len(words), len(set(words)))

    def test_curated_100_dataset_has_expected_size_and_categories(self) -> None:
        words = load_enrichment_benchmark_words("curated_100")
        metadata = load_enrichment_benchmark_metadata("curated_100")

        self.assertEqual(len(words), 100)
        self.assertEqual(len(words), len(set(words)))
        self.assertEqual(set(words), set(metadata))
        categories = set(metadata.values())
        self.assertEqual(
            categories,
            {
                "common_polysemous",
                "noun_verb_crossover",
                "adj_adv_ambiguity",
                "distinct_variant",
                "entity",
                "harder_tail",
            },
        )

    def test_run_enrichment_benchmark_writes_matrix_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmark"

            result = run_enrichment_benchmark(
                output_dir,
                dataset="default",
                prompt_modes=["word_only", "grounded"],
                model_names=["gpt-5.1-chat"],
                rank_provider=lambda word: 10,
                sense_provider=lambda lemma: [
                    {
                        "query_lemma": lemma,
                        "wn_synset_id": f"{lemma}.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": f"gloss for {lemma}",
                        "canonical_label": lemma,
                        "lemma_count": 10,
                    }
                ],
                run_case=lambda **kwargs: {
                    "model_name": kwargs["model_name"],
                    "prompt_mode": kwargs["prompt_mode"],
                    "lexeme_count": 2,
                    "selected_sense_count": 2,
                    "valid_response_count": 2,
                    "repair_count": 0,
                    "retry_count": 0,
                    "batch_duration_seconds": 1.25,
                    "average_latency_seconds": 0.62,
                    "average_confidence": 0.91,
                    "average_definition_chars": 80.0,
                    "average_usage_note_chars": 120.0,
                    "cefr_distribution": {"B1": 2},
                    "rows": [
                        {
                            "sense_id": "sn_lx_building_1",
                            "definition": "a structure",
                            "usage_note": "another form of the base word build",
                            "forms": {"verb_forms": {}},
                        }
                    ],
                },
            )

            self.assertTrue(result.summary_path.exists())
            self.assertEqual(result.payload["dataset"], "default")
            self.assertEqual(result.payload["prompt_modes"], ["word_only", "grounded"])
            self.assertEqual(result.payload["models"], ["gpt-5.1-chat"])
            self.assertEqual(
                result.payload["category_counts"],
                {
                    "common_polysemous": 4,
                    "distinct_variant": 1,
                    "entity": 1,
                    "noun_verb_crossover": 2,
                },
            )
            self.assertEqual(len(result.payload["runs"]), 2)
            self.assertEqual(
                {(row["model_name"], row["prompt_mode"]) for row in result.payload["runs"]},
                {
                    ("gpt-5.1-chat", "word_only"),
                    ("gpt-5.1-chat", "grounded"),
                },
            )
            self.assertEqual(result.payload["runs"][0]["rubric_summary"]["distinct_variant_rows"], 1)

    def test_run_enrichment_benchmark_resumes_from_case_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmark"
            call_log: list[str] = []

            def flaky_case_runner(**kwargs):
                call_log.append(kwargs["model_name"])
                checkpoint_path = kwargs["output_path"].with_suffix(".progress.json")
                completed_lexemes = list(kwargs.get("completed_lexemes") or [])
                if not checkpoint_path.exists():
                    checkpoint_path.write_text(
                        '{"completed_lexemes": ["right"], "rows": [{"sense_id": "sn_lx_right_1", "definition": "correct", "usage_note": "ok", "forms": {"verb_forms": {}}}], "repair_count": 0, "retry_count": 0}\n',
                        encoding="utf-8",
                    )
                    raise RuntimeError("right: transient invalid payload")
                if completed_lexemes != ["right"]:
                    raise RuntimeError(f"resume state missing: {completed_lexemes}")
                return {
                    "model_name": kwargs["model_name"],
                    "prompt_mode": kwargs["prompt_mode"],
                    "lexeme_count": 2,
                    "selected_sense_count": 2,
                    "valid_response_count": 2,
                    "repair_count": 1,
                    "retry_count": 1,
                    "batch_duration_seconds": 1.25,
                    "average_latency_seconds": 0.62,
                    "average_confidence": 0.91,
                    "average_definition_chars": 80.0,
                    "average_usage_note_chars": 120.0,
                    "cefr_distribution": {"B1": 2},
                    "rows": [
                        {
                            "sense_id": "sn_lx_right_1",
                            "definition": "correct",
                            "usage_note": "ok",
                            "forms": {"verb_forms": {}},
                        },
                        {
                            "sense_id": "sn_lx_open_1",
                            "definition": "not closed",
                            "usage_note": "ok",
                            "forms": {"verb_forms": {}},
                        },
                    ],
                }

            with self.assertRaisesRegex(RuntimeError, "transient invalid payload"):
                run_enrichment_benchmark(
                    output_dir,
                    dataset="default",
                    prompt_modes=["word_only"],
                    model_names=["gpt-5.1-chat"],
                    rank_provider=lambda word: 10,
                    sense_provider=lambda lemma: [
                        {
                            "query_lemma": lemma,
                            "wn_synset_id": f"{lemma}.n.01",
                            "part_of_speech": "noun",
                            "canonical_gloss": f"gloss for {lemma}",
                            "canonical_label": lemma,
                            "lemma_count": 10,
                        }
                    ],
                    run_case=flaky_case_runner,
                )

            result = run_enrichment_benchmark(
                output_dir,
                dataset="default",
                prompt_modes=["word_only"],
                model_names=["gpt-5.1-chat"],
                rank_provider=lambda word: 10,
                sense_provider=lambda lemma: [
                    {
                        "query_lemma": lemma,
                        "wn_synset_id": f"{lemma}.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": f"gloss for {lemma}",
                        "canonical_label": lemma,
                        "lemma_count": 10,
                    }
                ],
                run_case=flaky_case_runner,
            )

            self.assertEqual(call_log, ["gpt-5.1-chat", "gpt-5.1-chat"])
            self.assertTrue((output_dir / "gpt-5.1-chat.word_only.progress.json").exists())
            self.assertEqual(len(result.payload["runs"]), 1)
            self.assertEqual(result.payload["runs"][0]["valid_response_count"], 2)

    def test_run_enrichment_benchmark_exposes_streaming_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmark"

            seen_paths: dict[str, str] = {}

            def capturing_case_runner(**kwargs):
                seen_paths["rows_output_path"] = str(kwargs["rows_output_path"])
                seen_paths["failures_output_path"] = str(kwargs["failures_output_path"])
                return {
                    "model_name": kwargs["model_name"],
                    "prompt_mode": kwargs["prompt_mode"],
                    "lexeme_count": 2,
                    "selected_sense_count": 2,
                    "valid_response_count": 2,
                    "repair_count": 0,
                    "retry_count": 0,
                    "batch_duration_seconds": 1.25,
                    "average_latency_seconds": 0.62,
                    "average_confidence": 0.91,
                    "average_definition_chars": 80.0,
                    "average_usage_note_chars": 120.0,
                    "cefr_distribution": {"B1": 2},
                    "rows": [
                        {
                            "sense_id": "sn_lx_right_1",
                            "definition": "correct",
                            "usage_note": "ok",
                            "forms": {"verb_forms": {}},
                        }
                    ],
                }

            run_enrichment_benchmark(
                output_dir,
                dataset="default",
                prompt_modes=["word_only"],
                model_names=["gpt-5.1-chat"],
                rank_provider=lambda word: 10,
                sense_provider=lambda lemma: [
                    {
                        "query_lemma": lemma,
                        "wn_synset_id": f"{lemma}.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": f"gloss for {lemma}",
                        "canonical_label": lemma,
                        "lemma_count": 10,
                    }
                ],
                run_case=capturing_case_runner,
            )

            self.assertEqual(
                Path(seen_paths["rows_output_path"]).name,
                "gpt-5.1-chat.word_only.rows.jsonl",
            )
            self.assertEqual(
                Path(seen_paths["failures_output_path"]).name,
                "gpt-5.1-chat.word_only.failures.jsonl",
            )


if __name__ == "__main__":
    unittest.main()
