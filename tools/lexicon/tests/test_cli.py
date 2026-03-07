import io
import json
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
        self.assertIn("validate", stdout)
        self.assertIn("compile-export", stdout)
        self.assertIn("import-db", stdout)

    def test_build_base_command_emits_json_summary(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: {"run": 5, "set": 10}[word], lambda word: [{"wn_synset_id": f"{word}.n.01", "part_of_speech": "noun", "canonical_gloss": f"gloss for {word}", "canonical_label": word}])):
            code, stdout, _ = self.run_cli(["build-base", "Run", "SET", "run"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "build-base")
        self.assertEqual(payload["words"], ["run", "set"])
        self.assertEqual(payload["lexeme_count"], 2)
        self.assertEqual(payload["sense_count"], 2)

    def test_build_base_command_reports_dependency_errors(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", side_effect=LexiconDependencyError("WordNet corpus is unavailable")):
            code, _, stderr = self.run_cli(["build-base", "run"])

        self.assertEqual(code, 2)
        self.assertIn("WordNet corpus is unavailable", stderr)

    def test_build_base_command_writes_snapshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "snapshot"

            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: {"run": 5, "set": 10}[word], lambda word: [{"wn_synset_id": f"{word}.n.01", "part_of_speech": "noun", "canonical_gloss": f"gloss for {word}", "canonical_label": word}])):
                code, stdout, _ = self.run_cli(["build-base", "Run", "SET", "--output-dir", str(output_dir)])

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

    def test_enrich_command_reports_provider_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", side_effect=LexiconDependencyError("LEXICON_LLM_BASE_URL is required")):
                code, _, stderr = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible"])

            self.assertEqual(code, 2)
            self.assertIn("LEXICON_LLM_BASE_URL is required", stderr)

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
                code, stdout, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "run", "set"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "smoke-openai-compatible")
            self.assertEqual(payload["output_dir"], str(output_dir))
            self.assertEqual(payload["compiled_count"], 1)
            self.assertEqual(payload["enrichment_count"], 2)
            self.assertEqual(mocked_build.call_args.kwargs["words"], ["run", "set"])
            mocked_compile.assert_called_once()

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
                        "schema_version": "1.0.0",
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
                        "schema_version": "1.0.0",
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
                        "schema_version": "1.0.0",
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


if __name__ == "__main__":
    unittest.main()
