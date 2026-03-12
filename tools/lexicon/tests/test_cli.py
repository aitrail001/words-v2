import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.lexicon import cli
from tools.lexicon.enrich import EnrichmentRunResult
from tools.lexicon.errors import LexiconDependencyError


class CliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_top_level_help_lists_available_commands(self) -> None:
        code, stdout, _ = self.run_cli(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("build-base", stdout)
        self.assertIn("smoke-openai-compatible", stdout)
        self.assertIn("enrich", stdout)
        self.assertIn("rerank-senses", stdout)
        self.assertIn("compare-selection", stdout)
        self.assertIn("benchmark-selection", stdout)
        self.assertIn("validate", stdout)
        self.assertIn("compile-export", stdout)
        self.assertIn("import-db", stdout)

    def test_build_base_command_emits_json_summary(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: {"run": 5, "set": 10}[word], lambda word: [{"wn_synset_id": f"{word}.n.01", "part_of_speech": "noun", "canonical_gloss": f"gloss for {word}", "canonical_label": word}])):
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "Run", "SET", "run"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "build-base")
        self.assertEqual(payload["words"], ["run", "set"])
        self.assertEqual(payload["lexeme_count"], 2)
        self.assertEqual(payload["sense_count"], 2)

    def test_build_base_command_can_source_top_words_inventory(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: 10, lambda word: [])), \
             patch("tools.lexicon.cli._load_word_inventory_provider", return_value=lambda limit: ["The", "and", "co-op", "123"]):
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "--top-words", "4"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["inventory_mode"], "top_words")
        self.assertEqual(payload["requested_top_words"], 4)
        self.assertEqual(payload["words"], ["the", "and", "co-op"])

    def test_build_base_command_supports_rollout_stage_alias(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: 10, lambda word: [])), \
             patch("tools.lexicon.cli._load_word_inventory_provider", return_value=lambda limit: ["one", "two", "three"]):
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "--rollout-stage", "100"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["requested_top_words"], 100)
        self.assertEqual(payload["words"], ["one", "two", "three"])

    def test_build_base_command_requires_words_or_top_words(self) -> None:
        code, _, stderr = self.run_cli(["build-base"])

        self.assertEqual(code, 2)
        self.assertIn("requires seed words or --top-words", stderr)

    def test_build_base_command_reports_dependency_errors(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", side_effect=LexiconDependencyError("WordNet corpus is unavailable")):
            code, _, stderr = self.run_cli(["build-base", "run"])

        self.assertEqual(code, 2)
        self.assertIn("WordNet corpus is unavailable", stderr)

    def test_build_base_command_skips_existing_db_words_when_db_is_configured(self) -> None:
        fake_result = type("FakeBaseResult", (), {
            "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
            "senses": [object()],
            "concepts": [object()],
            "ambiguous_forms": [],
            "skipped_existing_canonical_words": ["set"],
        })()
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
             patch("tools.lexicon.cli._load_existing_db_words", return_value={"set"}) as mocked_existing, \
             patch("tools.lexicon.cli.build_base_records", return_value=fake_result) as mocked_build:
            code, stdout, _ = self.run_cli(["build-base", "--database-url", "postgresql://example/test", "run", "set"])
            callback = mocked_build.call_args.kwargs["existing_canonical_words_lookup"]
            self.assertIsNotNone(callback)
            self.assertEqual(callback(["run", "set"]), {"set"})
            mocked_existing.assert_called_once_with(["run", "set"], language="en", database_url="postgresql://example/test")

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["skip_existing_db"])
        self.assertEqual(payload["skipped_existing_db_count"], 1)

    def test_build_base_command_without_db_config_skips_lookup(self) -> None:
        fake_result = type("FakeBaseResult", (), {
            "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
            "senses": [object()],
            "concepts": [object()],
            "ambiguous_forms": [],
            "skipped_existing_canonical_words": [],
        })()
        with patch.dict(os.environ, {}, clear=True), \
             patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
             patch("tools.lexicon.cli._load_existing_db_words") as mocked_existing, \
             patch("tools.lexicon.cli.build_base_records", return_value=fake_result) as mocked_build:
            code, stdout, _ = self.run_cli(["build-base", "run"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertFalse(payload["skip_existing_db"])
        mocked_existing.assert_not_called()
        self.assertIsNone(mocked_build.call_args.kwargs["existing_canonical_words_lookup"])

    def test_build_base_command_rerun_existing_disables_db_skip_lookup(self) -> None:
        fake_result = type("FakeBaseResult", (), {
            "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
            "senses": [object()],
            "concepts": [object()],
            "ambiguous_forms": [],
            "skipped_existing_canonical_words": [],
        })()
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
             patch("tools.lexicon.cli._load_existing_db_words") as mocked_existing, \
             patch("tools.lexicon.cli.build_base_records", return_value=fake_result) as mocked_build:
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "run"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertFalse(payload["skip_existing_db"])
        self.assertEqual(payload["skipped_existing_db_count"], 0)
        mocked_existing.assert_not_called()
        self.assertIsNone(mocked_build.call_args.kwargs["existing_canonical_words_lookup"])

    def test_build_base_command_writes_snapshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "snapshot"

            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: {"run": 5, "set": 10}[word], lambda word: [{"wn_synset_id": f"{word}.n.01", "part_of_speech": "noun", "canonical_gloss": f"gloss for {word}", "canonical_label": word}])):
                code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "Run", "SET", "--output-dir", str(output_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "build-base")
            self.assertEqual(payload["output_dir"], str(output_dir))
            self.assertTrue((output_dir / "lexemes.jsonl").exists())
            self.assertTrue((output_dir / "senses.jsonl").exists())
            self.assertTrue((output_dir / "concepts.jsonl").exists())

    def test_enrich_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "enrichments.jsonl", enrichments=[object()])) as mocked_enrich:
                code, stdout, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            self.assertEqual(payload["enrichment_count"], 1)
            mocked_enrich.assert_called_once()

    def test_enrich_command_passes_provider_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "enrichments.jsonl", enrichments=[object()])) as mocked_enrich:
                code, stdout, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            mocked_enrich.assert_called_once()
            self.assertEqual(mocked_enrich.call_args.kwargs["provider_mode"], "openai_compatible")


    def test_enrich_command_passes_mode_concurrency_and_resume_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            checkpoint_path = snapshot_dir / "checkpoint.jsonl"
            failures_path = snapshot_dir / "failures.jsonl"
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "enrichments.jsonl", enrichments=[object()], lexeme_count=2, mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--mode",
                    "per_word",
                    "--max-concurrency",
                    "8",
                    "--resume",
                    "--checkpoint-path",
                    str(checkpoint_path),
                    "--failures-output",
                    str(failures_path),
                    "--max-failures",
                    "3",
                    "--request-delay-seconds",
                    "1.5",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["mode"], "per_word")
            self.assertEqual(payload["lexeme_count"], 2)
            self.assertEqual(mocked_enrich.call_args.kwargs["mode"], "per_word")
            self.assertEqual(mocked_enrich.call_args.kwargs["max_concurrency"], 8)
            self.assertTrue(mocked_enrich.call_args.kwargs["resume"])
            self.assertEqual(mocked_enrich.call_args.kwargs["checkpoint_path"], checkpoint_path)
            self.assertEqual(mocked_enrich.call_args.kwargs["failures_output"], failures_path)
            self.assertEqual(mocked_enrich.call_args.kwargs["max_failures"], 3)
            self.assertEqual(mocked_enrich.call_args.kwargs["request_delay_seconds"], 1.5)

    def test_enrich_command_reports_provider_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", side_effect=LexiconDependencyError("LEXICON_LLM_BASE_URL is required")):
                code, _, stderr = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible"])

            self.assertEqual(code, 2)
            self.assertIn("LEXICON_LLM_BASE_URL is required", stderr)


    def test_enrich_command_passes_node_provider_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "enrichments.jsonl", enrichments=[])) as mocked_enrich:
                code, stdout, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible_node"])

            self.assertEqual(code, 0)
            self.assertIn('"command": "enrich"', stdout)
            self.assertEqual(mocked_enrich.call_args.kwargs["provider_mode"], "openai_compatible_node")

    def test_openai_compatible_smoke_command_runs_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result) as mocked_build, \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "enrichments.jsonl", enrichments=[object(), object()])), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.compile_snapshot", return_value=[object()]) as mocked_compile:
                code, stdout, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "--max-words", "2", "--max-senses", "1", "run", "set"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "smoke-openai-compatible")
            self.assertEqual(payload["output_dir"], str(output_dir))
            self.assertEqual(payload["compiled_count"], 1)
            self.assertEqual(payload["enrichment_count"], 2)
            self.assertEqual(payload["requested_words"], ["run", "set"])
            self.assertEqual(payload["max_words"], 2)
            self.assertEqual(payload["max_senses"], 1)
            self.assertEqual(mocked_build.call_args.kwargs["words"], ["run", "set"])
            self.assertEqual(mocked_build.call_args.kwargs["max_senses"], 1)
            mocked_compile.assert_called_once()

    def test_openai_compatible_smoke_command_bounds_words_before_building(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result) as mocked_build, \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "enrichments.jsonl", enrichments=[object()])), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.compile_snapshot", return_value=[object()]):
                code, stdout, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "--max-words", "1", "run", "set", "lead"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["requested_words"], ["run", "set", "lead"])
            self.assertEqual(payload["words"], ["run"])
            self.assertEqual(mocked_build.call_args.kwargs["words"], ["run"])


    def test_openai_compatible_smoke_command_passes_provider_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result), \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "enrichments.jsonl", enrichments=[object()] )) as mocked_enrich, \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.compile_snapshot", return_value=[object()]):
                code, _, _ = self.run_cli(["smoke-openai-compatible", "--provider-mode", "openai_compatible_node", "--output-dir", str(output_dir), "run"])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_enrich.call_args.kwargs["provider_mode"], "openai_compatible_node")

    def test_openai_compatible_smoke_command_passes_model_and_reasoning_effort_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result), \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "enrichments.jsonl", enrichments=[object()] )) as mocked_enrich, \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.compile_snapshot", return_value=[object()]):
                code, _, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "--model", "gpt-5.4", "--reasoning-effort", "low", "run"])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_enrich.call_args.kwargs["model_name"], "gpt-5.4")
            self.assertEqual(mocked_enrich.call_args.kwargs["reasoning_effort"], "low")

    def test_openai_compatible_smoke_command_reports_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result), \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "enrichments.jsonl", enrichments=[object()])), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=["bad enrichment"]):
                code, stdout, stderr = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "run"])

            self.assertEqual(code, 2)
            self.assertEqual(stderr, "")
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "smoke-openai-compatible")
            self.assertEqual(payload["error_count"], 1)
            self.assertEqual(payload["errors"], ["bad enrichment"])

    def test_build_base_command_defaults_max_senses_to_eight(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["build-base", "run"])

        self.assertEqual(args.max_senses, 8)
        self.assertFalse(args.rerun_existing)

    def test_smoke_openai_compatible_command_defaults_to_bounded_values(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["smoke-openai-compatible", "--output-dir", "/tmp/lexicon-smoke", "run"])

        self.assertEqual(args.max_senses, 2)
        self.assertEqual(args.max_words, 1)

    def test_rerank_senses_command_defaults_candidate_source_to_candidates(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["rerank-senses", "--snapshot-dir", "/tmp/lexicon-snapshot"])

        self.assertEqual(args.candidate_source, "candidates")

    def test_rerank_senses_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            output_path = snapshot_dir / "sense_reranks.jsonl"
            fake_result = type("FakeRerankRunResult", (), {"output_path": output_path, "rows": [{"lexeme_id": "lx_run"}]})()
            with patch("tools.lexicon.cli.run_rerank", return_value=fake_result) as mocked_rerank:
                code, stdout, _ = self.run_cli(["rerank-senses", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "rerank-senses")
            self.assertEqual(payload["rerank_count"], 1)
            self.assertEqual(payload["output"], str(output_path))
            mocked_rerank.assert_called_once()

    def test_rerank_senses_command_passes_provider_model_reasoning_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            output_path = snapshot_dir / "sense_reranks.jsonl"
            fake_result = type("FakeRerankRunResult", (), {"output_path": output_path, "rows": [{"lexeme_id": "lx_run"}]})()
            with patch("tools.lexicon.cli.run_rerank", return_value=fake_result) as mocked_rerank:
                code, _, _ = self.run_cli([
                    "rerank-senses",
                    "--snapshot-dir", str(snapshot_dir),
                    "--provider-mode", "openai_compatible_node",
                    "--model", "gpt-5.4",
                    "--reasoning-effort", "low",
                    "--candidate-source", "candidates",
                    "--candidate-limit", "10",
                    "run",
                ])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_rerank.call_args.kwargs["provider_mode"], "openai_compatible_node")
            self.assertEqual(mocked_rerank.call_args.kwargs["model_name"], "gpt-5.4")
            self.assertEqual(mocked_rerank.call_args.kwargs["reasoning_effort"], "low")
            self.assertEqual(mocked_rerank.call_args.kwargs["candidate_source"], "candidates")
            self.assertEqual(mocked_rerank.call_args.kwargs["candidate_limit"], 10)
            self.assertEqual(mocked_rerank.call_args.kwargs["words"], ["run"])

    def test_rerank_senses_command_passes_each_candidate_source_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            output_path = snapshot_dir / "sense_reranks.jsonl"
            fake_result = type("FakeRerankRunResult", (), {"output_path": output_path, "rows": [{"lexeme_id": "lx_run"}]})()
            for candidate_source in ("selected_only", "candidates", "full_wordnet"):
                with self.subTest(candidate_source=candidate_source):
                    with patch("tools.lexicon.cli.run_rerank", return_value=fake_result) as mocked_rerank:
                        code, _, _ = self.run_cli([
                            "rerank-senses",
                            "--snapshot-dir", str(snapshot_dir),
                            "--candidate-source", candidate_source,
                            "run",
                        ])

                    self.assertEqual(code, 0)
                    self.assertEqual(mocked_rerank.call_args.kwargs["candidate_source"], candidate_source)

    def test_compare_selection_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            rerank_file = snapshot_dir / "sense_reranks.jsonl"
            rerank_file.write_text("", encoding="utf-8")
            output_path = snapshot_dir / "comparison.json"
            with patch("tools.lexicon.cli.compare_selection_artifacts", return_value={
                "compared_lexeme_count": 1,
                "changed_lexeme_count": 1,
                "changes": [{"lemma": "run"}],
            }) as mocked_compare:
                code, stdout, _ = self.run_cli([
                    "compare-selection",
                    "--snapshot-dir", str(snapshot_dir),
                    "--rerank-file", str(rerank_file),
                    "--output", str(output_path),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "compare-selection")
            self.assertEqual(payload["changed_lexeme_count"], 1)
            self.assertEqual(payload["output"], str(output_path))
            mocked_compare.assert_called_once()

    def test_benchmark_selection_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"
            fake_result = type(
                "FakeBenchmarkSelectionRunResult",
                (),
                {
                    "summary_path": output_dir / "summary.json",
                    "payload": {
                        "output_dir": str(output_dir),
                        "datasets": [{"dataset": "tuning", "rerank_runs": []}],
                    },
                },
            )()
            with patch("tools.lexicon.cli.run_selection_benchmark", return_value=fake_result) as mocked_benchmark:
                code, stdout, _ = self.run_cli(["benchmark-selection", "--output-dir", str(output_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "benchmark-selection")
            self.assertEqual(payload["summary"], str(output_dir / "summary.json"))
            self.assertEqual(payload["datasets"][0]["dataset"], "tuning")
            mocked_benchmark.assert_called_once()

    def test_score_selection_risk_command_reports_risk_band_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            output_path = snapshot_dir / "selection_decisions.jsonl"
            fake_result = type("FakeSelectionRiskRunResult", (), {"output_path": output_path, "rows": [{"risk_band": "deterministic_only"}, {"risk_band": "rerank_recommended"}]})()
            with patch("tools.lexicon.cli.score_selection_risk", return_value=fake_result) as mocked_score:
                code, stdout, _ = self.run_cli(["score-selection-risk", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "score-selection-risk")
            self.assertEqual(payload["decision_count"], 2)
            self.assertEqual(payload["output"], str(output_path))
            self.assertEqual(payload["risk_band_counts"], {"deterministic_only": 1, "rerank_recommended": 1})
            mocked_score.assert_called_once()

    def test_prepare_review_command_reports_review_queue_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            decisions_path = snapshot_dir / "selection_decisions.jsonl"
            decisions_path.write_text("", encoding="utf-8")
            output_path = snapshot_dir / "selection_decisions.reviewed.jsonl"
            review_queue_path = snapshot_dir / "review_queue.jsonl"
            fake_result = type("FakePrepareReviewRunResult", (), {"output_path": output_path, "rows": [{"lemma": "run"}], "review_queue_output": review_queue_path, "review_rows": [{"lemma": "run", "review_required": True}]})()
            with patch("tools.lexicon.cli.prepare_review", return_value=fake_result) as mocked_prepare:
                code, stdout, _ = self.run_cli(["prepare-review", "--snapshot-dir", str(snapshot_dir), "--decisions", str(decisions_path)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "prepare-review")
            self.assertEqual(payload["decision_count"], 1)
            self.assertEqual(payload["review_count"], 1)
            self.assertEqual(payload["output"], str(output_path))
            self.assertEqual(payload["review_queue_output"], str(review_queue_path))
            mocked_prepare.assert_called_once()

    def test_score_selection_risk_command_reports_rerank_recommended_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            output_path = snapshot_dir / "selection_decisions.jsonl"
            fake_result = type("FakeSelectionRiskRunResult", (), {"output_path": output_path, "rows": [{"lemma": "bank", "risk_band": "rerank_recommended"}, {"lemma": "run", "risk_band": "deterministic_only"}]})()
            with patch("tools.lexicon.cli.score_selection_risk", return_value=fake_result) as mocked_score:
                code, stdout, _ = self.run_cli(["score-selection-risk", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "score-selection-risk")
            self.assertEqual(payload["decision_count"], 2)
            self.assertEqual(payload["rerank_recommended_count"], 1)
            self.assertEqual(payload["output"], str(output_path))
            mocked_score.assert_called_once()

    def test_prepare_review_command_reports_rerank_and_review_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            decisions_path = snapshot_dir / "selection_decisions.jsonl"
            decisions_path.write_text("", encoding="utf-8")
            output_path = snapshot_dir / "selection_decisions.reviewed.jsonl"
            queue_path = snapshot_dir / "review_queue.jsonl"
            fake_result = type(
                "FakePrepareReviewRunResult",
                (),
                {
                    "output_path": output_path,
                    "rows": [{"lemma": "bank", "auto_accepted": True}, {"lemma": "case", "review_required": True}],
                    "review_queue_output": queue_path,
                    "review_rows": [{"lemma": "case"}],
                    "reranked_lexeme_count": 1,
                },
            )()
            with patch("tools.lexicon.cli.prepare_review", return_value=fake_result) as mocked_prepare:
                code, stdout, _ = self.run_cli([
                    "prepare-review",
                    "--snapshot-dir", str(snapshot_dir),
                    "--decisions", str(decisions_path),
                    "--review-queue-output", str(queue_path),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "prepare-review")
            self.assertEqual(payload["decision_count"], 2)
            self.assertEqual(payload["reranked_lexeme_count"], 1)
            self.assertEqual(payload["review_required_count"], 1)
            self.assertEqual(payload["review_queue_output"], str(queue_path))
            mocked_prepare.assert_called_once()

    def test_prepare_review_command_passes_provider_and_candidate_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            decisions_path = snapshot_dir / "selection_decisions.jsonl"
            decisions_path.write_text("", encoding="utf-8")
            output_path = snapshot_dir / "selection_decisions.reviewed.jsonl"
            fake_result = type(
                "FakePrepareReviewRunResult",
                (),
                {
                    "output_path": output_path,
                    "rows": [],
                    "review_queue_output": None,
                    "review_rows": [],
                    "reranked_lexeme_count": 0,
                },
            )()
            with patch("tools.lexicon.cli.prepare_review", return_value=fake_result) as mocked_prepare:
                code, _, _ = self.run_cli([
                    "prepare-review",
                    "--snapshot-dir", str(snapshot_dir),
                    "--decisions", str(decisions_path),
                    "--output", str(output_path),
                    "--provider-mode", "openai_compatible_node",
                    "--model", "gpt-5.4",
                    "--reasoning-effort", "low",
                    "--candidate-limit", "12",
                    "--candidate-source", "candidates",
                ])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_prepare.call_args.kwargs["provider_mode"], "openai_compatible_node")
            self.assertEqual(mocked_prepare.call_args.kwargs["model_name"], "gpt-5.4")
            self.assertEqual(mocked_prepare.call_args.kwargs["reasoning_effort"], "low")
            self.assertEqual(mocked_prepare.call_args.kwargs["candidate_limit"], 12)
            self.assertEqual(mocked_prepare.call_args.kwargs["candidate_source"], "candidates")

    def test_benchmark_selection_command_passes_rerank_modes_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"
            fake_result = type(
                "FakeBenchmarkSelectionRunResult",
                (),
                {
                    "summary_path": output_dir / "summary.json",
                    "payload": {"output_dir": str(output_dir), "datasets": []},
                },
            )()
            with patch("tools.lexicon.cli.run_selection_benchmark", return_value=fake_result) as mocked_benchmark:
                code, _, _ = self.run_cli([
                    "benchmark-selection",
                    "--output-dir", str(output_dir),
                    "--dataset", "tuning",
                    "--dataset", "holdout",
                    "--max-senses", "8",
                    "--with-rerank",
                    "--provider-mode", "openai_compatible_node",
                    "--model", "gpt-5.4",
                    "--reasoning-effort", "low",
                    "--candidate-limit", "12",
                    "--candidate-source", "selected_only",
                    "--candidate-source", "full_wordnet",
                ])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_benchmark.call_args.kwargs["datasets"], ["tuning", "holdout"])
            self.assertEqual(mocked_benchmark.call_args.kwargs["max_senses"], 8)
            self.assertTrue(mocked_benchmark.call_args.kwargs["with_rerank"])
            self.assertEqual(mocked_benchmark.call_args.kwargs["provider_mode"], "openai_compatible_node")
            self.assertEqual(mocked_benchmark.call_args.kwargs["model_name"], "gpt-5.4")
            self.assertEqual(mocked_benchmark.call_args.kwargs["reasoning_effort"], "low")
            self.assertEqual(mocked_benchmark.call_args.kwargs["candidate_limit"], 12)
            self.assertEqual(mocked_benchmark.call_args.kwargs["candidate_sources"], ["selected_only", "full_wordnet"])

    def test_validate_command_validates_snapshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "language": "en",
                        "wordfreq_rank": 5,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_run_1",
                        "lexeme_id": "lx_run",
                        "wn_synset_id": "run.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "move fast by using your legs",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "enrichments.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "sense_id": "sn_lx_run_1",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "cefr_level": "A1",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": ["runner"],
                        },
                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "generation_run_id": "run-123",
                        "confidence": 0.9,
                        "review_status": "approved",
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, stdout, _ = self.run_cli(["validate", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "validate")
            self.assertEqual(payload["scope"], "snapshot")
            self.assertEqual(payload["error_count"], 0)

    def test_validate_command_accepts_compiled_input_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "words.enriched.jsonl"
            compiled_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "normalized_form": "run",
                        "source_provenance": [{"source": "wordfreq"}],
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "A1",
                        "frequency_rank": 5,
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": ["runner"],
                        },
                        "senses": [
                            {
                                "sense_id": "sn_lx_run_1",
                                "pos": "verb",
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "definition": "to move quickly on foot",
                                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                "synonyms": ["jog"],
                                "antonyms": ["walk"],
                                "collocations": ["run fast"],
                                "grammar_patterns": ["run + adverb"],
                                "usage_note": "Common everyday verb.",
                            }
                        ],
                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, stdout, _ = self.run_cli(["validate", "--compiled-input", str(compiled_path)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "validate")
            self.assertEqual(payload["scope"], "compiled")
            self.assertEqual(payload["error_count"], 0)

    def test_validate_command_accepts_compiled_path_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "words.enriched.jsonl"
            compiled_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "normalized_form": "run",
                        "source_provenance": [{"source": "wordfreq"}],
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "A1",
                        "frequency_rank": 5,
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": ["runner"],
                        },
                        "senses": [
                            {
                                "sense_id": "sn_lx_run_1",
                                "pos": "verb",
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "definition": "to move quickly on foot",
                                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                "synonyms": ["jog"],
                                "antonyms": ["walk"],
                                "collocations": ["run fast"],
                                "grammar_patterns": ["run + adverb"],
                                "usage_note": "Common everyday verb.",
                            }
                        ],
                        "confusable_words": [],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, stdout, _ = self.run_cli(["validate", "--compiled-path", str(compiled_path)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "validate")
            self.assertEqual(payload["scope"], "compiled")
            self.assertEqual(payload["error_count"], 0)


    def test_compile_export_command_writes_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            output_path = snapshot_dir / "words.enriched.jsonl"
            (snapshot_dir / "lexemes.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "language": "en",
                        "wordfreq_rank": 5,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_run_1",
                        "lexeme_id": "lx_run",
                        "wn_synset_id": "run.v.01",
                        "part_of_speech": "verb",
                        "canonical_gloss": "move fast by using your legs",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "enrichments.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "sense_id": "sn_lx_run_1",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "cefr_level": "A1",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": ["runner"],
                        },
                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "generation_run_id": "run-123",
                        "confidence": 0.9,
                        "review_status": "approved",
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, stdout, _ = self.run_cli(["compile-export", "--snapshot-dir", str(snapshot_dir), "--output", str(output_path)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "compile-export")
            self.assertEqual(payload["compiled_count"], 1)
            self.assertTrue(output_path.exists())
            compiled_rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(compiled_rows[0]["word"], "run")

    def test_import_db_command_runs_real_import_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "words.enriched.jsonl"
            compiled_path.write_text(
                json.dumps({
                    "schema_version": "1.0.0",
                    "word": "run",
                    "part_of_speech": ["verb"],
                    "cefr_level": "A1",
                    "frequency_rank": 5,
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "senses": [{"sense_id": "sn_lx_run_1", "pos": "verb", "primary_domain": "general", "secondary_domains": [], "register": "neutral", "definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "synonyms": [], "antonyms": [], "collocations": [], "grammar_patterns": [], "usage_note": ""}],
                    "confusable_words": [],
                    "generated_at": "2026-03-07T00:00:00Z"
                }) + "\n",
                encoding="utf-8",
            )

            with patch("tools.lexicon.cli.run_import_file", return_value={"created_words": 1, "updated_words": 0, "created_meanings": 1, "updated_meanings": 0}) as mocked_import:
                code, stdout, _ = self.run_cli([
                    "import-db",
                    "--input",
                    str(compiled_path),
                    "--source-type",
                    "lexicon_snapshot",
                    "--source-reference",
                    "snapshot-20260307",
                    "--language",
                    "en",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "import-db")
            self.assertFalse(payload["dry_run"])
            self.assertEqual(payload["summary"]["created_words"], 1)
            mocked_import.assert_called_once_with(
                compiled_path,
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260307",
                language="en",
            )

    def test_import_db_command_supports_dry_run_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "words.enriched.jsonl"
            compiled_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "normalized_form": "run",
                        "source_provenance": [{"source": "wordfreq"}],
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "A1",
                        "frequency_rank": 5,
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": ["runner"],
                        },
                        "senses": [
                            {
                                "sense_id": "sn_lx_run_1",
                                "pos": "verb",
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "definition": "to move quickly on foot",
                                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                "synonyms": ["jog"],
                                "antonyms": ["walk"],
                                "collocations": ["run fast"],
                                "grammar_patterns": ["run + adverb"],
                                "usage_note": "Common everyday verb.",
                            }
                        ],
                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, stdout, _ = self.run_cli(["import-db", "--input", str(compiled_path), "--dry-run"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "import-db")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["row_count"], 1)
            self.assertEqual(payload["sense_count"], 1)
            self.assertEqual(payload["example_count"], 1)
            self.assertEqual(payload["relation_count"], 3)


if __name__ == "__main__":
    unittest.main()

    def test_compile_export_command_passes_decision_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            decisions_path = Path(tmpdir) / "selection_decisions.jsonl"
            decisions_path.write_text("", encoding="utf-8")
            output_path = Path(tmpdir) / "words.enriched.jsonl"

            with patch("tools.lexicon.cli.compile_snapshot", return_value=[object()]) as mocked_compile:
                code, stdout, _ = self.run_cli([
                    "compile-export",
                    "--snapshot-dir", str(snapshot_dir),
                    "--output", str(output_path),
                    "--decisions", str(decisions_path),
                    "--decision-filter", "mode_c_safe",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["decision_filter"], "mode_c_safe")
            self.assertEqual(payload["decisions"], str(decisions_path))
            self.assertEqual(mocked_compile.call_args.kwargs["decision_filter"], "mode_c_safe")
            self.assertEqual(mocked_compile.call_args.kwargs["decisions_path"], decisions_path)

    def test_compile_export_command_rejects_decisions_without_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            decisions_path = Path(tmpdir) / "selection_decisions.jsonl"
            decisions_path.write_text("", encoding="utf-8")
            output_path = Path(tmpdir) / "words.enriched.jsonl"

            code, _, stderr = self.run_cli([
                "compile-export",
                "--snapshot-dir", str(snapshot_dir),
                "--output", str(output_path),
                "--decisions", str(decisions_path),
            ])

            self.assertEqual(code, 2)
            self.assertIn("requires --decision-filter", stderr)
