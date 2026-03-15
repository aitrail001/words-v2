import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrichment_benchmark import (
    _default_case_runner,
    load_enrichment_benchmark_metadata,
    load_enrichment_benchmark_words,
    run_enrichment_benchmark,
)
from tools.lexicon.models import LexemeRecord, SenseRecord


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

    def test_default_case_runner_retries_failed_lemma_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "case.json"
            progress_path = output_path.with_suffix(".progress.json")
            rows_path = output_path.with_suffix(".rows.jsonl")
            failures_path = output_path.with_suffix(".failures.jsonl")
            settings = LexiconSettings(
                output_root=Path(tmpdir),
                llm_base_url="https://example.test",
                llm_model="gpt-5.1",
                llm_api_key="test-key",
                llm_transport="openai_compatible",
                llm_reasoning_effort=None,
                llm_timeout_seconds=60,
            )
            lexemes = [
                LexemeRecord(
                    snapshot_id="snap",
                    lexeme_id="lx_right",
                    lemma="right",
                    language="en",
                    wordfreq_rank=10,
                    is_wordnet_backed=True,
                    source_refs=["wordfreq"],
                    created_at="2026-03-16T00:00:00Z",
                ),
                LexemeRecord(
                    snapshot_id="snap",
                    lexeme_id="lx_open",
                    lemma="open",
                    language="en",
                    wordfreq_rank=11,
                    is_wordnet_backed=True,
                    source_refs=["wordfreq"],
                    created_at="2026-03-16T00:00:00Z",
                ),
            ]
            senses = [
                SenseRecord(
                    snapshot_id="snap",
                    sense_id="sn_lx_right_1",
                    lexeme_id="lx_right",
                    wn_synset_id="right.a.01",
                    part_of_speech="adjective",
                    canonical_gloss="correct",
                    selection_reason="test",
                    sense_order=1,
                    is_high_polysemy=False,
                    created_at="2026-03-16T00:00:00Z",
                ),
                SenseRecord(
                    snapshot_id="snap",
                    sense_id="sn_lx_open_1",
                    lexeme_id="lx_open",
                    wn_synset_id="open.a.01",
                    part_of_speech="adjective",
                    canonical_gloss="not closed",
                    selection_reason="test",
                    sense_order=1,
                    is_high_polysemy=False,
                    created_at="2026-03-16T00:00:00Z",
                ),
            ]

            class FakeClient:
                response_schema_fallback_count = 0

            attempts = {"right": 0, "open": 0}

            def fake_generate(*, client, lexeme, senses, prompt_mode):
                attempts[lexeme.lemma] += 1
                if lexeme.lemma == "right" and attempts["right"] == 1:
                    raise RuntimeError("transient gateway failure")
                return (
                    [
                        {
                            "sense_id": senses[0].sense_id,
                            "definition": f"{lexeme.lemma} definition",
                            "examples": [{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                            "cefr_level": "A1",
                            "primary_domain": "general",
                            "secondary_domains": [],
                            "register": "neutral",
                            "synonyms": [],
                            "antonyms": [],
                            "collocations": [],
                            "grammar_patterns": [],
                            "usage_note": "ok",
                            "forms": {
                                "plural_forms": [],
                                "verb_forms": {},
                                "comparative": None,
                                "superlative": None,
                                "derivations": [],
                            },
                            "confusable_words": [],
                            "confidence": 0.9,
                            "translations": {
                                locale: {"definition": "x", "usage_note": "y", "examples": [f"{lexeme.lemma} translated"]}
                                for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                            },
                        }
                    ],
                    {"repair_count": 0, "retry_count": 0},
                )

            with patch("tools.lexicon.enrichment_benchmark.OpenAICompatibleResponsesClient", return_value=FakeClient()):
                with patch("tools.lexicon.enrichment_benchmark._generate_validated_word_payload_with_stats", side_effect=fake_generate):
                    first = _default_case_runner(
                        lexemes=lexemes,
                        senses=senses,
                        output_path=output_path,
                        checkpoint_path=progress_path,
                        rows_output_path=rows_path,
                        failures_output_path=failures_path,
                        completed_lexemes=[],
                        provider_mode="openai_compatible",
                        model_name="gpt-5.1",
                        prompt_mode="word_only",
                        settings=settings,
                    )
                    second = _default_case_runner(
                        lexemes=lexemes,
                        senses=senses,
                        output_path=output_path,
                        checkpoint_path=progress_path,
                        rows_output_path=rows_path,
                        failures_output_path=failures_path,
                        completed_lexemes=[],
                        provider_mode="openai_compatible",
                        model_name="gpt-5.1",
                        prompt_mode="word_only",
                        settings=settings,
                    )

            self.assertEqual(first["failed_lexemes"], ["right"])
            self.assertEqual(first["failed_lexeme_count"], 1)
            self.assertEqual(second["failed_lexemes"], [])
            self.assertEqual(second["failed_lexeme_count"], 0)
            self.assertEqual(second["valid_response_count"], 2)
            self.assertEqual(attempts["right"], 2)
            self.assertEqual(attempts["open"], 1)
            progress = output_path.with_suffix(".progress.json").read_text(encoding="utf-8")
            self.assertIn('"failed_lexemes": []', progress)

    def test_default_case_runner_persists_response_schema_fallback_count_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "case.json"
            progress_path = output_path.with_suffix(".progress.json")
            rows_path = output_path.with_suffix(".rows.jsonl")
            failures_path = output_path.with_suffix(".failures.jsonl")
            settings = LexiconSettings(
                output_root=Path(tmpdir),
                llm_base_url="https://example.test",
                llm_model="gpt-5.1",
                llm_api_key="test-key",
                llm_transport="openai_compatible",
                llm_reasoning_effort=None,
                llm_timeout_seconds=60,
            )
            lexeme = LexemeRecord(
                snapshot_id="snap",
                lexeme_id="lx_right",
                lemma="right",
                language="en",
                wordfreq_rank=10,
                is_wordnet_backed=True,
                source_refs=["wordfreq"],
                created_at="2026-03-16T00:00:00Z",
            )
            sense = SenseRecord(
                snapshot_id="snap",
                sense_id="sn_lx_right_1",
                lexeme_id="lx_right",
                wn_synset_id="right.a.01",
                part_of_speech="adjective",
                canonical_gloss="correct",
                selection_reason="test",
                sense_order=1,
                is_high_polysemy=False,
                created_at="2026-03-16T00:00:00Z",
            )

            class FakeClient:
                def __init__(self):
                    self.response_schema_fallback_count = 3

            fake_row = {
                "sense_id": sense.sense_id,
                "definition": "correct",
                "examples": [{"sentence": "right example", "difficulty": "A1"}],
                "cefr_level": "A1",
                "primary_domain": "general",
                "secondary_domains": [],
                "register": "neutral",
                "synonyms": [],
                "antonyms": [],
                "collocations": [],
                "grammar_patterns": [],
                "usage_note": "ok",
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "confusable_words": [],
                "confidence": 0.9,
                "translations": {
                    locale: {"definition": "x", "usage_note": "y", "examples": ["translated example"]}
                    for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                },
            }

            with patch("tools.lexicon.enrichment_benchmark.OpenAICompatibleResponsesClient", return_value=FakeClient()):
                with patch("tools.lexicon.enrichment_benchmark._generate_validated_word_payload_with_stats", return_value=([fake_row], {"repair_count": 0, "retry_count": 0})):
                    first = _default_case_runner(
                        lexemes=[lexeme],
                        senses=[sense],
                        output_path=output_path,
                        checkpoint_path=progress_path,
                        rows_output_path=rows_path,
                        failures_output_path=failures_path,
                        completed_lexemes=[],
                        provider_mode="openai_compatible",
                        model_name="gpt-5.1",
                        prompt_mode="word_only",
                        settings=settings,
                    )

            progress_path.write_text(
                '{\n'
                '  "completed_lexemes": [],\n'
                '  "failed_lexemes": [],\n'
                '  "rows": [],\n'
                '  "failure_rows": [],\n'
                '  "latencies": [],\n'
                '  "definition_lengths": [],\n'
                '  "usage_note_lengths": [],\n'
                '  "confidences": [],\n'
                '  "cefr_distribution": {},\n'
                '  "repair_count": 0,\n'
                '  "retry_count": 0,\n'
                '  "response_schema_fallback_count": 3\n'
                '}\n',
                encoding="utf-8",
            )

            class ZeroFallbackClient:
                response_schema_fallback_count = 0

            with patch("tools.lexicon.enrichment_benchmark.OpenAICompatibleResponsesClient", return_value=ZeroFallbackClient()):
                with patch("tools.lexicon.enrichment_benchmark._generate_validated_word_payload_with_stats", return_value=([fake_row], {"repair_count": 0, "retry_count": 0})):
                    second = _default_case_runner(
                        lexemes=[lexeme],
                        senses=[sense],
                        output_path=output_path,
                        checkpoint_path=progress_path,
                        rows_output_path=rows_path,
                        failures_output_path=failures_path,
                        completed_lexemes=[],
                        provider_mode="openai_compatible",
                        model_name="gpt-5.1",
                        prompt_mode="word_only",
                        settings=settings,
                    )

            self.assertEqual(first["response_schema_fallback_count"], 3)
            self.assertEqual(second["response_schema_fallback_count"], 3)


if __name__ == "__main__":
    unittest.main()
