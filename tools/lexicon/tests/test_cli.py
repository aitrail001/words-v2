import io
import csv
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from tools.lexicon import cli
from tools.lexicon.enrich import EnrichmentRunResult
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.tests.test_enrich import EnrichSnapshotTests, _test_phonetics


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

    def run_cli_via_sys_argv(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["python -m tools.lexicon.cli", *argv]), redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = cli.main()
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def run_cli_skip_guard(self, argv: list[str]) -> tuple[int, str, str]:
        with patch.dict(os.environ, {cli._LEXICON_VENV_GUARD_BYPASS_ENV: "1"}):
            return self.run_cli(argv)

    def _write_resume_modes_snapshot(self, snapshot_dir: Path) -> None:
        EnrichSnapshotTests()._write_resume_modes_snapshot(snapshot_dir)

    def _write_single_snapshot(self, snapshot_dir: Path) -> None:
        EnrichSnapshotTests()._write_snapshot(snapshot_dir)

    def _existing_alpha_compiled_row(self) -> dict[str, object]:
        return {
            "schema_version": "1.1.0",
            "entry_id": "lx_alpha",
            "entry_type": "word",
            "normalized_form": "alpha",
            "source_provenance": [{"source": "wordnet"}],
            "entity_category": "general",
            "word": "alpha",
            "part_of_speech": ["noun"],
            "cefr_level": "A1",
            "frequency_rank": 1,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [
                {
                    "sense_id": "sn_lx_alpha_1",
                    "wn_synset_id": "alpha.n.01",
                    "pos": "noun",
                    "sense_kind": "standard_meaning",
                    "decision": "keep_standard",
                    "base_word": None,
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "definition": "existing alpha",
                    "examples": [{"sentence": "alpha existing", "difficulty": "A1"}],
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": [],
                    "grammar_patterns": [],
                    "usage_note": "existing alpha note",
                    "enrichment_id": "en_alpha_existing",
                    "generation_run_id": "existing-run",
                    "model_name": "test-model",
                    "prompt_version": "v1",
                    "confidence": 0.9,
                    "generated_at": "2026-04-08T00:00:00Z",
                    "translations": {
                        "zh-Hans": {"definition": "zh:existing alpha", "usage_note": "zh:existing alpha note", "examples": ["zh:alpha existing"]},
                        "es": {"definition": "es:existing alpha", "usage_note": "es:existing alpha note", "examples": ["es:alpha existing"]},
                        "ar": {"definition": "ar:existing alpha", "usage_note": "ar:existing alpha note", "examples": ["ar:alpha existing"]},
                        "pt-BR": {"definition": "pt:existing alpha", "usage_note": "pt:existing alpha note", "examples": ["pt:alpha existing"]},
                        "ja": {"definition": "ja:existing alpha", "usage_note": "ja:existing alpha note", "examples": ["ja:alpha existing"]},
                    },
                }
            ],
            "confusable_words": [],
            "generated_at": "2026-04-08T00:00:00Z",
            "phonetics": _test_phonetics(),
        }

    def _existing_alpha_core_row(self) -> dict[str, object]:
        row = self._existing_alpha_compiled_row()
        sense = dict(row["senses"][0])  # type: ignore[index]
        sense.pop("translations", None)
        row["senses"] = [sense]
        return row

    def _existing_alpha_translation_rows(self) -> list[dict[str, object]]:
        return [
            {
                "entry_id": "lx_alpha",
                "sense_id": "sn_lx_alpha_1",
                "locale": locale,
                "definition": definition,
                "usage_note": usage_note,
                "examples": [example],
                "generated_at": "2026-04-08T00:00:00Z",
                "generation_run_id": "existing-run",
                "model_name": "test-model",
                "prompt_version": "v1",
                "status": "completed",
            }
            for locale, definition, usage_note, example in [
                ("zh-Hans", "zh:existing alpha", "zh:existing alpha note", "zh:alpha existing"),
                ("es", "es:existing alpha", "es:existing alpha note", "es:alpha existing"),
                ("ar", "ar:existing alpha", "ar:existing alpha note", "ar:alpha existing"),
                ("pt-BR", "pt:existing alpha", "pt:existing alpha note", "pt:alpha existing"),
                ("ja", "ja:existing alpha", "ja:existing alpha note", "ja:alpha existing"),
            ]
        ]

    def test_top_level_help_lists_available_commands(self) -> None:
        code, stdout, _ = self.run_cli(["--help"])

        self.assertEqual(code, 0)
        self.assertIn("build-base", stdout)
        self.assertIn("smoke-openai-compatible", stdout)
        self.assertIn("enrich", stdout)
        self.assertIn("benchmark-selection", stdout)
        self.assertIn("benchmark-enrichment", stdout)
        self.assertIn("build-phrases", stdout)
        self.assertIn("phrase-build-base", stdout)
        self.assertIn("reference-build-base", stdout)
        self.assertIn("batch-prepare", stdout)
        self.assertIn("batch-submit", stdout)
        self.assertIn("batch-status", stdout)
        self.assertIn("batch-ingest", stdout)
        self.assertIn("batch-retry", stdout)
        self.assertIn("batch-qc", stdout)
        self.assertIn("review-materialize", stdout)
        self.assertIn("validate", stdout)
        self.assertIn("import-db", stdout)
        self.assertIn("voice-generate", stdout)
        self.assertIn("voice-import-db", stdout)

    def test_voice_generate_rejects_retry_failed_only_with_skip_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "voice-out"
            log_file = Path(tmpdir) / "voice-generate.runtime.log"
            code, _, stderr = self.run_cli([
                "voice-generate",
                "--input",
                "approved.jsonl",
                "--output-dir",
                str(output_dir),
                "--log-file",
                str(log_file),
                "--resume",
                "--retry-failed-only",
                "--skip-failed",
            ])

            self.assertEqual(code, 2)
            self.assertIn("cannot be combined", stderr)
            self.assertTrue(log_file.exists())

    def test_voice_generate_emits_runtime_progress_events(self) -> None:
        def fake_run_voice_generation(**kwargs):
            progress_callback = kwargs["progress_callback"]
            progress_callback(
                "voice-generate-start",
                message="Voice generation started",
                input="approved.jsonl",
                output_dir="voice-out",
            )
            progress_callback(
                "voice-generate-plan",
                message="Voice generation planned",
                planned_count=6,
                eligible_word_count=1,
                eligible_phrase_count=0,
            )
            progress_callback(
                "voice-generate-complete",
                message="Voice generation complete",
                planned_count=6,
                generated_count=6,
                failed_count=0,
            )
            return {
                "planned_count": 6,
                "scheduled_count": 6,
                "generated_count": 6,
                "existing_count": 0,
                "failed_count": 0,
                "skipped_completed_count": 0,
                "skipped_failed_count": 0,
                "retried_failed_count": 0,
                "manifest_path": "voice-out/voice_manifest.jsonl",
                "errors_path": "voice-out/voice_errors.jsonl",
                "plan_path": "voice-out/voice_plan.jsonl",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "voice-out"
            log_file = Path(tmpdir) / "voice-generate.runtime.log"
            with patch("tools.lexicon.cli.run_voice_generation", side_effect=fake_run_voice_generation):
                code, stdout, stderr = self.run_cli([
                    "voice-generate",
                    "--input",
                    "approved.jsonl",
                    "--output-dir",
                    str(output_dir),
                    "--log-file",
                    str(log_file),
                    "--locales",
                    "en-US",
                ])

            self.assertEqual(code, 0)
            self.assertIn("voice-generate-start", stderr)
            self.assertIn("voice-generate-plan", stderr)
            self.assertIn("voice-generate-complete", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["planned_count"], 6)
            self.assertTrue(log_file.exists())

    def test_voice_sync_storage_dry_run_emits_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "voice-sync-storage.runtime.log"
            with patch("tools.lexicon.cli.run_voice_storage_sync", return_value={
                "matched_count": 6,
                "updated_count": 0,
                "dry_run": True,
                "storage_kind": "s3",
                "storage_base": "https://cdn.example.com/voice",
                "fallback_storage_kind": "http",
                "fallback_storage_base": "https://backup.example.com/voice",
            }):
                code, stdout, _ = self.run_cli([
                    "voice-sync-storage",
                    "--source-reference",
                    "voice-roundtrip",
                    "--storage-kind",
                    "s3",
                    "--storage-base",
                    "https://cdn.example.com/voice",
                    "--fallback-storage-kind",
                    "http",
                    "--fallback-storage-base",
                    "https://backup.example.com/voice",
                    "--log-file",
                    str(log_file),
                    "--dry-run",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "voice-sync-storage")
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["matched_count"], 6)
            self.assertEqual(payload["fallback_storage_kind"], "http")
            self.assertEqual(payload["fallback_storage_base"], "https://backup.example.com/voice")
            self.assertTrue(log_file.exists())

    def test_voice_import_db_emits_runtime_progress_events(self) -> None:
        def fake_run_voice_import_file(*args, progress_callback=None, **kwargs):
            assert progress_callback is not None
            progress_callback(row={"entry_id": "word:bank", "entry_type": "word", "word": "bank", "_progress_label": "Importing 1/2: bank", "content_scope": "word", "locale": "en-US", "voice_role": "female"}, completed_rows=1, total_rows=2)
            progress_callback(row={"entry_id": "word:bank", "entry_type": "word", "word": "bank", "_progress_label": "Importing 2/2: bank", "content_scope": "definition", "locale": "en-US", "voice_role": "male"}, completed_rows=2, total_rows=2)
            progress_callback(row={"entry_id": "word:harbor", "entry_type": "word", "word": "harbor", "_progress_label": "Skipping existing word: harbor", "content_scope": "word", "locale": "en-GB", "voice_role": "female"}, completed_rows=2, total_rows=2)
            return {"created_assets": 1, "updated_assets": 0, "skipped_rows": 1, "failed_rows": 0}

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "voice-import-db.runtime.log"
            with patch("tools.lexicon.cli.load_voice_manifest_rows", return_value=[{"entry_id": "word:bank"}, {"entry_id": "word:harbor"}]), \
                 patch("tools.lexicon.cli.run_voice_import_file", side_effect=fake_run_voice_import_file) as mocked_run:
                code, stdout, stderr = self.run_cli([
                    "voice-import-db",
                    "--input",
                    "voice_manifest.jsonl",
                    "--log-file",
                    str(log_file),
                ])

            self.assertEqual(code, 0)
            self.assertIn("item-progress", stderr)
            self.assertIn("item_type=voice-manifest-group", stderr)
            self.assertIn("entry_label=bank", stderr)
            self.assertIn("action=skip", stderr)
            self.assertNotIn(" row=", stderr)
            self.assertEqual(mocked_run.call_args.kwargs["error_mode"], "continue")
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "voice-import-db")
            self.assertFalse(payload["dry_run"])
            self.assertTrue(log_file.exists())

    def test_build_base_command_emits_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "build-base.runtime.log"
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: {"run": 5, "set": 10}[word], lambda word: [{"wn_synset_id": f"{word}.n.01", "part_of_speech": "noun", "canonical_gloss": f"gloss for {word}", "canonical_label": word}])):
                code, stdout, _ = self.run_cli([
                    "build-base",
                    "--rerun-existing",
                    "--log-file",
                    str(log_file),
                    "Run",
                    "SET",
                    "run",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "build-base")
            self.assertEqual(payload["words"], ["run", "set"])
            self.assertEqual(payload["lexeme_count"], 2)
            self.assertTrue(log_file.exists())

    def test_build_base_command_can_source_top_words_inventory(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: 10, lambda word: [])), \
             patch("tools.lexicon.cli._load_word_inventory_provider", return_value=lambda limit: ["The", "and", "co-op", "123"]):
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "--top-words", "4"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["inventory_mode"], "top_words")
        self.assertEqual(payload["requested_top_words"], 4)
        self.assertEqual(payload["words"], ["the", "and", "co-op"])

    def test_build_base_command_top_words_does_not_require_wordnet(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", side_effect=LexiconDependencyError("WordNet corpus is unavailable")), \
             patch("tools.lexicon.cli._load_word_inventory_provider", return_value=lambda limit: ["The", "and", "co-op"]):
            code, stdout, stderr = self.run_cli(["build-base", "--rerun-existing", "--top-words", "3"])

        self.assertEqual(code, 0)
        self.assertIn("command-complete", stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["inventory_mode"], "top_words")
        self.assertEqual(payload["requested_top_words"], 3)
        self.assertEqual(payload["words"], ["the", "and", "co-op"])

    def test_build_base_command_top_words_applies_tail_exclusions_dataset(self) -> None:
        with patch("tools.lexicon.cli._load_build_base_providers", return_value=(lambda word: 10, lambda word: [])), \
             patch("tools.lexicon.cli._load_word_inventory_provider", return_value=lambda limit: ["a", "an", "the", "cat"]):
            code, stdout, _ = self.run_cli(["build-base", "--rerun-existing", "--top-words", "4"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["words"], ["the", "cat"])

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

    def test_build_base_command_emits_runtime_progress_log_without_changing_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "snapshot"
            log_file = output_dir / "build-base.runtime.log"
            fake_result = type(
                "FakeBaseResult",
                (),
                {
                    "lexemes": [type("Lexeme", (), {"lemma": "run"})(), type("Lexeme", (), {"lemma": "set"})()],
                    "ambiguous_forms": [],
                    "skipped_existing_canonical_words": [],
                    "excluded_tail_canonical_words": [],
                },
            )()

            def fake_build_base_records(**kwargs):
                kwargs["progress_callback"](
                    word="run",
                    entry_id="lx_run",
                    completed_items=1,
                    total_items=2,
                    status="built",
                )
                kwargs["progress_callback"](
                    word="set",
                    entry_id="lx_set",
                    completed_items=2,
                    total_items=2,
                    status="built",
                )
                return fake_result

            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", side_effect=fake_build_base_records), \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}):
                code, stdout, _ = self.run_cli([
                    "build-base",
                    "--rerun-existing",
                    "--output-dir",
                    str(output_dir),
                    "--log-level",
                    "debug",
                    "--log-file",
                    str(log_file),
                    "run",
                    "set",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "build-base")
            self.assertEqual(payload["words"], ["run", "set"])
            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            events = [row["event"] for row in log_rows]
            self.assertIn("command-start", events)
            self.assertIn("item-progress", events)
            self.assertIn("command-complete", events)
            progress_rows = [row for row in log_rows if row["event"] == "item-progress"]
            self.assertTrue(any(row["fields"]["item_type"] == "word" and row["fields"]["entry_id"] == "lx_run" for row in progress_rows))

    def test_enrich_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir)])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            self.assertEqual(payload["enrichment_count"], 1)
            mocked_enrich.assert_called_once()

    def test_enrich_command_rejects_retry_failed_only_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            code, _, stderr = self.run_cli([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--retry-failed-only",
            ])

        self.assertEqual(code, 2)
        self.assertIn("--retry-failed-only requires --resume", stderr)

    def test_enrich_command_rejects_skip_failed_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            code, _, stderr = self.run_cli([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--skip-failed",
            ])

        self.assertEqual(code, 2)
        self.assertIn("--skip-failed requires --resume", stderr)

    def test_enrich_command_rejects_retry_failed_only_with_skip_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            code, _, stderr = self.run_cli([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--resume",
                "--retry-failed-only",
                "--skip-failed",
            ])

        self.assertEqual(code, 2)
        self.assertIn("--retry-failed-only and --skip-failed cannot be combined", stderr)

    def test_enrich_command_passes_provider_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            mocked_enrich.assert_called_once()
            self.assertEqual(mocked_enrich.call_args.kwargs["provider_mode"], "openai_compatible")

    def test_enrich_command_passes_log_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            log_file = snapshot_dir / "runtime.log"
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--log-level",
                    "debug",
                    "--log-file",
                    str(log_file),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            self.assertEqual(mocked_enrich.call_args.kwargs["log_level"], "debug")
            self.assertEqual(mocked_enrich.call_args.kwargs["log_file"], log_file)

    def test_enrich_command_uses_lower_retry_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, _, _ = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir)])

        self.assertEqual(code, 0)
        self.assertEqual(mocked_enrich.call_args.kwargs["transient_retries"], 2)
        self.assertEqual(mocked_enrich.call_args.kwargs["validation_retries"], 1)

    def test_enrich_command_passes_retry_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, _, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--transient-retries",
                    "6",
                    "--validation-retries",
                    "3",
                ])

        self.assertEqual(code, 0)
        self.assertEqual(mocked_enrich.call_args.kwargs["transient_retries"], 6)
        self.assertEqual(mocked_enrich.call_args.kwargs["validation_retries"], 3)


    def test_enrich_command_passes_concurrency_and_resume_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            checkpoint_path = snapshot_dir / "checkpoint.jsonl"
            failures_path = snapshot_dir / "failures.jsonl"
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], lexeme_count=2, mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
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
                    "--max-new-completed-lexemes",
                    "250",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["mode"], "per_word")
            self.assertEqual(payload["lexeme_count"], 2)
            self.assertEqual(mocked_enrich.call_args.kwargs["max_concurrency"], 8)
            self.assertTrue(mocked_enrich.call_args.kwargs["resume"])
            self.assertEqual(mocked_enrich.call_args.kwargs["checkpoint_path"], checkpoint_path)
            self.assertEqual(mocked_enrich.call_args.kwargs["failures_output"], failures_path)
            self.assertEqual(mocked_enrich.call_args.kwargs["max_failures"], 3)
            self.assertEqual(mocked_enrich.call_args.kwargs["request_delay_seconds"], 1.5)
            self.assertEqual(mocked_enrich.call_args.kwargs["max_new_completed_lexemes"], 250)

    def test_enrich_command_forwards_retry_failed_only_when_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--resume",
                    "--retry-failed-only",
                ])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "enrich")
        self.assertTrue(mocked_enrich.call_args.kwargs["retry_failed_only"])

    def test_enrich_command_forwards_skip_failed_when_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")) as mocked_enrich:
                code, stdout, _ = self.run_cli([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--resume",
                    "--skip-failed",
                ])

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["command"], "enrich")
        self.assertTrue(mocked_enrich.call_args.kwargs["skip_failed"])

    def test_enrich_command_rejects_removed_mode_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)

            code, _, stderr = self.run_cli([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--mode",
                "per_sense",
            ])

        self.assertNotEqual(code, 0)
        self.assertIn("unrecognized arguments: --mode per_sense", stderr)

    def test_enrich_command_rejects_removed_mode_flag_via_real_sys_argv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment") as mocked_enrich:
                code, _, stderr = self.run_cli_via_sys_argv([
                    "enrich",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--mode",
                    "per_word",
                ])

        self.assertNotEqual(code, 0)
        self.assertIn("unrecognized arguments: --mode per_word", stderr)
        mocked_enrich.assert_not_called()

    def test_enrich_command_reports_provider_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", side_effect=LexiconDependencyError("LEXICON_LLM_BASE_URL is required")):
                code, _, stderr = self.run_cli(["enrich", "--snapshot-dir", str(snapshot_dir), "--provider-mode", "openai_compatible"])

        self.assertEqual(code, 2)
        self.assertIn("LEXICON_LLM_BASE_URL is required", stderr)

    def test_phrase_build_base_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "phrases.jsonl"
            input_path.write_text(
                "\n".join([
                    json.dumps({"phrase": "Take off", "phrase_kind": "phrasal_verb"}),
                    json.dumps({"phrase": "take off", "phrase_kind": "phrasal_verb"}),
                ]) + "\n",
                encoding="utf-8",
            )
            output_dir = root / "phrase-snapshot"

            code, stdout, stderr = self.run_cli([
                "phrase-build-base",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ])

            self.assertEqual(code, 0)
            self.assertIn("command-complete", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "phrase-build-base")
            self.assertEqual(payload["phrase_count"], 1)
            self.assertTrue((output_dir / "phrases.jsonl").exists())

    def test_build_phrases_command_accepts_multiple_csv_sources_and_merges_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_a = root / "reviewed_phrasals.csv"
            source_b = root / "reviewed_idioms.csv"
            fieldnames = [
                "expression",
                "original_order",
                "source",
                "reviewed_as",
                "difficulty",
                "commonality",
                "added",
                "confidence",
            ]
            with source_a.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "expression": "Take off",
                    "original_order": "1",
                    "source": "phrasals",
                    "reviewed_as": "phrasal verb",
                    "difficulty": "B1",
                    "commonality": "high",
                    "added": "yes",
                    "confidence": "0.92",
                })
            with source_b.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "expression": "take off",
                    "original_order": "4",
                    "source": "idioms",
                    "reviewed_as": "multi-word verb",
                    "difficulty": "B2",
                    "commonality": "medium",
                    "added": "no",
                    "confidence": "0.71",
                })
                writer.writerow({
                    "expression": "Break a leg",
                    "original_order": "5",
                    "source": "idioms",
                    "reviewed_as": "idiom",
                    "difficulty": "B2",
                    "commonality": "medium",
                    "added": "yes",
                    "confidence": "0.85",
                })
            output_dir = root / "phrase-snapshot"

            code, stdout, stderr = self.run_cli([
                "build-phrases",
                "--output-dir",
                str(output_dir),
                str(source_a),
                str(source_b),
            ])

            self.assertEqual(code, 0)
            self.assertIn("command-complete", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "build-phrases")
            self.assertEqual(payload["source_count"], 2)
            self.assertEqual(payload["input_count"], 3)
            self.assertEqual(payload["phrase_count"], 2)
            self.assertEqual(payload["deduped_count"], 1)
            rows = [
                json.loads(line)
                for line in (output_dir / "phrases.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["normalized_form"], "take off")
            self.assertEqual(len(rows[0]["source_provenance"]), 2)

    def test_reference_build_base_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "references.jsonl"
            input_path.write_text(
                "\n".join([
                    json.dumps({
                        "display_form": "Melbourne",
                        "reference_type": "place",
                        "translation_mode": "localized_display",
                        "brief_description": "A major city in Australia.",
                        "pronunciation": "MEL-burn",
                    }),
                    json.dumps({
                        "display_form": "Melbourne",
                        "reference_type": "place",
                        "translation_mode": "localized_display",
                        "brief_description": "Duplicate row",
                        "pronunciation": "MEL-burn",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            output_dir = root / "reference-snapshot"

            code, stdout, stderr = self.run_cli([
                "reference-build-base",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ])

            self.assertEqual(code, 0)
            self.assertIn("command-complete", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "reference-build-base")
            self.assertEqual(payload["reference_count"], 1)
            self.assertTrue((output_dir / "references.jsonl").exists())

    def test_batch_prepare_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "entries.jsonl"
            input_path.write_text(
                "\n".join([
                    json.dumps({"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"}),
                    json.dumps({"entry_kind": "phrase", "entry_id": "ph_take_off", "display_form": "take off"}),
                ]) + "\n",
                encoding="utf-8",
            )
            output_dir = root / "batch"

            code, stdout, stderr = self.run_cli([
                "batch-prepare",
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
                "--model",
                "gpt-5-mini",
                "--prompt-version",
                "v1",
            ])

            self.assertEqual(code, 0)
            self.assertIn("command-complete", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "batch-prepare")
            self.assertEqual(payload["request_count"], 2)
            self.assertTrue((output_dir / "batch_requests.jsonl").exists())


    def test_enrich_command_passes_node_provider_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=snapshot_dir / "words.enriched.jsonl", enrichments=[], mode="per_word")) as mocked_enrich:
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
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object(), object()], mode="per_word")), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.load_compiled_rows", return_value=[object()]) as mocked_load:
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
            mocked_load.assert_called_once_with(output_dir / "words.enriched.jsonl")

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
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.load_compiled_rows", return_value=[object()]):
                code, stdout, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "--max-words", "1", "run", "set", "lead"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["requested_words"], ["run", "set", "lead"])
            self.assertEqual(payload["words"], ["run"])
            self.assertEqual(mocked_build.call_args.kwargs["words"], ["run"])

    def test_openai_compatible_smoke_command_uses_direct_words_enriched_output_without_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "smoke"
            fake_result = type("FakeBaseResult", (), {
                "lexemes": [type("Lexeme", (), {"lemma": "run"})()],
                "senses": [object()],
                "concepts": [object()],
            })()
            compiled_row = {
                "entry_id": "lx_run",
                "entry_type": "word",
                "word": "run",
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
                "senses": [{"definition": "to move quickly"}],
            }
            with patch("tools.lexicon.cli._load_build_base_providers", return_value=(object(), object())), \
                 patch("tools.lexicon.cli.build_base_records", return_value=fake_result), \
                 patch("tools.lexicon.cli.write_base_snapshot", return_value={"lexemes": output_dir / "lexemes.jsonl"}), \
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object()])), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.load_compiled_rows", return_value=[compiled_row]) as mocked_load, \
                 patch("tools.lexicon.cli.compile_snapshot") as mocked_compile:
                code, stdout, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "run"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["compiled_output"], str(output_dir / "words.enriched.jsonl"))
            self.assertEqual(payload["compiled_count"], 1)
            mocked_load.assert_called_once_with(output_dir / "words.enriched.jsonl")
            mocked_compile.assert_not_called()
            self.assertEqual(compiled_row["phonetics"]["us"]["ipa"], "/rʌn/")


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
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word" )) as mocked_enrich, \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.load_compiled_rows", return_value=[object()]):
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
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word" )) as mocked_enrich, \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=[]), \
                 patch("tools.lexicon.cli.load_compiled_rows", return_value=[object()]):
                code, _, _ = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "--model", "gpt-5.4", "--reasoning-effort", "low", "run"])

            self.assertEqual(code, 0)
            self.assertEqual(mocked_enrich.call_args.kwargs["model_name"], "gpt-5.4")
            self.assertEqual(mocked_enrich.call_args.kwargs["reasoning_effort"], "low")

    def test_benchmark_enrichment_command_accepts_reasoning_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"
            fake_result = type(
                "FakeBenchmarkResult",
                (),
                {
                    "summary_path": output_dir / "summary.json",
                    "payload": {
                        "output_dir": str(output_dir),
                        "dataset": "default",
                        "prompt_modes": ["word_only"],
                        "models": ["gpt-5.1"],
                        "runs": [],
                    },
                },
            )()
            with patch("tools.lexicon.cli.run_enrichment_benchmark", return_value=fake_result) as mocked_benchmark:
                code, _, _ = self.run_cli(
                    [
                        "benchmark-enrichment",
                        "--output-dir",
                        str(output_dir),
                        "--model",
                        "gpt-5.1",
                        "--reasoning-effort",
                        "none",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(mocked_benchmark.call_args.kwargs["reasoning_effort"], "none")

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
                 patch("tools.lexicon.cli.run_enrichment", return_value=EnrichmentRunResult(output_path=output_dir / "words.enriched.jsonl", enrichments=[object()], mode="per_word")), \
                 patch("tools.lexicon.cli.validate_snapshot_files", return_value=["bad enrichment"]):
                code, stdout, stderr = self.run_cli(["smoke-openai-compatible", "--output-dir", str(output_dir), "run"])

            self.assertEqual(code, 2)
            self.assertIn("command-failure", stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "smoke-openai-compatible")
            self.assertEqual(payload["error_count"], 1)
            self.assertEqual(payload["errors"], ["bad enrichment"])

    def test_build_base_command_defaults_max_senses_to_eight(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["build-base", "run"])

        self.assertEqual(args.max_senses, 8)
        self.assertFalse(args.rerun_existing)

    def test_shared_logging_flags_default_for_non_enrichment_commands(self) -> None:
        parser = cli.build_parser()

        build_base_args = parser.parse_args(["build-base", "run"])
        batch_prepare_args = parser.parse_args(["batch-prepare", "--input", "/tmp/input.jsonl", "--output-dir", "/tmp/out"])
        import_db_args = parser.parse_args(["import-db", "--input", "/tmp/compiled.jsonl"])
        export_db_args = parser.parse_args(["export-db", "--output", "/tmp/export.jsonl"])

        self.assertEqual(build_base_args.log_level, "info")
        self.assertIsNone(build_base_args.log_file)
        self.assertEqual(batch_prepare_args.log_level, "info")
        self.assertIsNone(batch_prepare_args.log_file)
        self.assertEqual(import_db_args.log_level, "info")
        self.assertIsNone(import_db_args.log_file)
        self.assertEqual(export_db_args.log_level, "info")
        self.assertIsNone(export_db_args.log_file)

    def test_smoke_openai_compatible_command_defaults_to_bounded_values(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["smoke-openai-compatible", "--output-dir", "/tmp/lexicon-smoke", "run"])

        self.assertEqual(args.max_senses, 2)
        self.assertEqual(args.max_words, 1)






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

    def test_benchmark_enrichment_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "benchmarks"
            fake_result = type(
                "FakeBenchmarkResult",
                (),
                {
                    "summary_path": output_dir / "summary.json",
                    "payload": {
                        "output_dir": str(output_dir),
                        "dataset": "default",
                        "prompt_modes": ["word_only", "grounded"],
                        "models": ["gpt-5.1-chat", "gpt-5.4"],
                        "runs": [],
                    },
                },
            )()
            with patch("tools.lexicon.cli.run_enrichment_benchmark", return_value=fake_result) as mocked_benchmark:
                code, stdout, _ = self.run_cli(
                    [
                        "benchmark-enrichment",
                        "--output-dir",
                        str(output_dir),
                        "--prompt-mode",
                        "word_only",
                        "--prompt-mode",
                        "grounded",
                        "--model",
                        "gpt-5.1-chat",
                        "--model",
                        "gpt-5.4",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "benchmark-enrichment")
            self.assertEqual(payload["dataset"], "default")
            self.assertEqual(payload["prompt_modes"], ["word_only", "grounded"])
            self.assertEqual(payload["models"], ["gpt-5.1-chat", "gpt-5.4"])
            mocked_benchmark.assert_called_once()

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
                        "phonetics": {
                            "us": {"ipa": "/rʌn/", "confidence": 0.99},
                            "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                            "au": {"ipa": "/rɐn/", "confidence": 0.97},
                        },
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
                        "phonetics": {
                            "us": {"ipa": "/rʌn/", "confidence": 0.99},
                            "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                            "au": {"ipa": "/rɐn/", "confidence": 0.97},
                        },
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
            mocked_import.assert_called_once()
            self.assertEqual(mocked_import.call_args.args[0], compiled_path)
            self.assertEqual(mocked_import.call_args.kwargs["source_type"], "lexicon_snapshot")
            self.assertEqual(mocked_import.call_args.kwargs["source_reference"], "snapshot-20260307")
            self.assertEqual(mocked_import.call_args.kwargs["language"], "en")
            self.assertTrue(callable(mocked_import.call_args.kwargs["progress_callback"]))

    def test_import_db_command_emits_runtime_progress_log_without_changing_stdout(self) -> None:
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
                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        "senses": [],
                        "confusable_words": [],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            log_file = Path(tmpdir) / "import-db.runtime.log"

            def fake_run_import_file(path, **kwargs):
                kwargs["progress_callback"](
                    row={"entry_id": "lx_run", "entry_type": "word"},
                    completed_rows=1,
                    total_rows=1,
                )
                return {"created_words": 1, "updated_words": 0}

            with patch("tools.lexicon.cli.run_import_file", side_effect=fake_run_import_file):
                code, stdout, _ = self.run_cli([
                    "import-db",
                    "--input",
                    str(compiled_path),
                    "--log-level",
                    "debug",
                    "--log-file",
                    str(log_file),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "import-db")
            self.assertEqual(payload["summary"]["created_words"], 1)
            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            events = [row["event"] for row in log_rows]
            self.assertIn("command-start", events)
            self.assertIn("item-progress", events)
            self.assertIn("command-complete", events)
            progress_rows = [row for row in log_rows if row["event"] == "item-progress"]
            self.assertTrue(any(row["fields"]["item_type"] == "row" and row["fields"]["completed_rows"] == 1 for row in progress_rows))

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

    def test_import_db_parser_accepts_import_mode_staging(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["import-db", "--input", "/tmp/compiled.jsonl", "--import-mode", "staging"])

        self.assertEqual(args.import_mode, "staging")

    def test_import_db_parser_accepts_on_conflict_mode(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(["import-db", "--input", "/tmp/compiled.jsonl", "--on-conflict", "skip"])

        self.assertEqual(args.on_conflict, "skip")

    def test_import_db_command_forwards_import_mode(self) -> None:
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
                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        "senses": [],
                        "confusable_words": [],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tools.lexicon.cli.run_import_file", return_value={"created_words": 1}) as mocked_import:
                code, stdout, _ = self.run_cli([
                    "import-db",
                    "--input",
                    str(compiled_path),
                    "--import-mode",
                    "staging",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["summary"]["created_words"], 1)
            self.assertEqual(mocked_import.call_args.kwargs["import_mode"], "staging")

    def test_import_db_command_forwards_on_conflict_mode(self) -> None:
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
                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        "senses": [],
                        "confusable_words": [],
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tools.lexicon.cli.run_import_file", return_value={"created_words": 1}) as mocked_import:
                code, stdout, _ = self.run_cli([
                    "import-db",
                    "--input",
                    str(compiled_path),
                    "--on-conflict",
                    "skip",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["summary"]["created_words"], 1)
            self.assertEqual(mocked_import.call_args.kwargs["on_conflict"], "skip")

    def test_export_db_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "approved.jsonl"
            with patch(
                "tools.lexicon.cli.export_db_fixture",
                return_value={
                    "output_path": str(output_path),
                    "row_count": 2,
                    "word_count": 1,
                    "phrase_count": 1,
                    "reference_count": 0,
                },
            ) as mocked_export:
                code, stdout, _ = self.run_cli([
                    "export-db",
                    "--output",
                    str(output_path),
                    "--max-words",
                    "10",
                    "--max-phrases",
                    "20",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "export-db")
            self.assertEqual(payload["word_count"], 1)
            self.assertEqual(payload["phrase_count"], 1)
            mocked_export.assert_called_once_with(output_path, max_words=10, max_phrases=20)

    def test_split_enrich_artifact_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "words.enriched.jsonl"
            core_path = Path(tmpdir) / "words.enriched.core.jsonl"
            translations_path = Path(tmpdir) / "words.translations.jsonl"
            core_checkpoint_path = Path(tmpdir) / "enrich.core.checkpoint.jsonl"
            translations_checkpoint_path = Path(tmpdir) / "enrich.translations.checkpoint.jsonl"

            with patch(
                "tools.lexicon.cli.split_legacy_enrich_artifact",
                return_value={
                    "compiled_input": str(compiled_path),
                    "core_output": str(core_path),
                    "translations_output": str(translations_path),
                    "core_row_count": 1,
                    "translation_row_count": 5,
                    "core_checkpoint": str(core_checkpoint_path),
                    "translations_checkpoint": str(translations_checkpoint_path),
                },
            ) as mocked_split:
                code, stdout, _ = self.run_cli([
                    "split-enrich-artifact",
                    "--compiled-input",
                    str(compiled_path),
                    "--core-output",
                    str(core_path),
                    "--translations-output",
                    str(translations_path),
                    "--core-checkpoint-path",
                    str(core_checkpoint_path),
                    "--translations-checkpoint-path",
                    str(translations_checkpoint_path),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "split-enrich-artifact")
            self.assertEqual(payload["core_row_count"], 1)
            self.assertEqual(payload["translation_row_count"], 5)
            self.assertEqual(mocked_split.call_args.kwargs["compiled_input_path"], compiled_path)
            self.assertEqual(mocked_split.call_args.kwargs["core_output_path"], core_path)
            self.assertEqual(mocked_split.call_args.kwargs["translations_output_path"], translations_path)
            self.assertEqual(mocked_split.call_args.kwargs["core_checkpoint_path"], core_checkpoint_path)
            self.assertEqual(mocked_split.call_args.kwargs["translations_checkpoint_path"], translations_checkpoint_path)

    def test_merge_enrich_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            core_path = Path(tmpdir) / "words.enriched.core.jsonl"
            translations_path = Path(tmpdir) / "words.translations.jsonl"
            output_path = Path(tmpdir) / "words.enriched.jsonl"
            log_file = Path(tmpdir) / "merge.runtime.log"

            with patch(
                "tools.lexicon.cli.merge_staged_enrichment_artifacts",
                return_value={
                    "core_input": str(core_path),
                    "translations_input": str(translations_path),
                    "output": str(output_path),
                    "merged_row_count": 1,
                },
            ) as mocked_merge:
                code, stdout, _ = self.run_cli([
                    "merge-enrich",
                    "--core-input",
                    str(core_path),
                    "--translations-input",
                    str(translations_path),
                    "--output",
                    str(output_path),
                    "--log-level",
                    "debug",
                    "--log-file",
                    str(log_file),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "merge-enrich")
            self.assertEqual(payload["merged_row_count"], 1)
            self.assertEqual(mocked_merge.call_args.kwargs["core_input_path"], core_path)
            self.assertEqual(mocked_merge.call_args.kwargs["translations_input_path"], translations_path)
            self.assertEqual(mocked_merge.call_args.kwargs["output_path"], output_path)
            self.assertIsNotNone(mocked_merge.call_args.kwargs["runtime_logger"])

    def test_enrich_core_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            output_path = snapshot_dir / "words.enriched.core.jsonl"
            runtime_output_path = snapshot_dir / "words.enriched.core.runtime.jsonl"

            with patch(
                "tools.lexicon.cli.run_core_enrichment",
                return_value=type(
                    "Result",
                    (),
                    {
                        "output_path": output_path,
                        "runtime_output_path": runtime_output_path,
                        "lexeme_count": 10,
                        "core_row_count": 8,
                    },
                )(),
            ) as mocked_run:
                code, stdout, _ = self.run_cli([
                    "enrich-core",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--resume",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich-core")
            self.assertEqual(payload["lexeme_count"], 10)
            self.assertEqual(payload["core_row_count"], 8)
            self.assertEqual(mocked_run.call_args.args[0], snapshot_dir)

    def test_enrich_translations_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            output_path = snapshot_dir / "words.translations.jsonl"

            with patch(
                "tools.lexicon.cli.run_translation_enrichment",
                return_value=type(
                    "Result",
                    (),
                    {
                        "output_path": output_path,
                        "sense_count": 7,
                        "translation_row_count": 35,
                    },
                )(),
            ) as mocked_run:
                code, stdout, _ = self.run_cli([
                    "enrich-translations",
                    "--snapshot-dir",
                    str(snapshot_dir),
                    "--resume",
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich-translations")
            self.assertEqual(payload["sense_count"], 7)
            self.assertEqual(payload["translation_row_count"], 35)
            self.assertEqual(mocked_run.call_args.args[0], snapshot_dir)

    def test_enrich_command_placeholder_cli_preserves_existing_output_and_backfills_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            write_jsonl(snapshot_dir / "words.enriched.jsonl", [self._existing_alpha_compiled_row()])
            write_jsonl(
                snapshot_dir / "enrich.failures.jsonl",
                [{
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "status": "failed",
                    "generation_run_id": "failed-run",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }],
            )

            code, stdout, stderr = self.run_cli_skip_guard([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--request-delay-seconds",
                "0",
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich")
            self.assertEqual(payload["enrichment_count"], 3)
            rows = read_jsonl(snapshot_dir / "words.enriched.jsonl")
            self.assertEqual({row["entry_id"] for row in rows}, {"lx_alpha", "lx_run", "lx_play"})
            self.assertEqual(sum(1 for row in rows if row["entry_id"] == "lx_alpha"), 1)
            self.assertEqual(
                {row["lexeme_id"] for row in read_jsonl(snapshot_dir / "enrich.checkpoint.jsonl")},
                {"lx_alpha", "lx_run", "lx_play"},
            )
            self.assertEqual(
                {row["lexeme_id"] for row in read_jsonl(snapshot_dir / "enrich.decisions.jsonl")},
                {"lx_alpha", "lx_run", "lx_play"},
            )

    def test_enrich_command_placeholder_cli_resume_failure_modes(self) -> None:
        with tempfile.TemporaryDirectory() as retry_tmpdir:
            retry_snapshot_dir = Path(retry_tmpdir)
            self._write_resume_modes_snapshot(retry_snapshot_dir)
            write_jsonl(
                retry_snapshot_dir / "enrich.failures.jsonl",
                [{
                    "lexeme_id": "lx_run",
                    "entry_id": "lx_run",
                    "entry_type": "word",
                    "lemma": "run",
                    "display_form": "run",
                    "status": "failed",
                    "generation_run_id": "failed-run",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }],
            )

            code, stdout, stderr = self.run_cli_skip_guard([
                "enrich",
                "--snapshot-dir",
                str(retry_snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--resume",
                "--retry-failed-only",
                "--request-delay-seconds",
                "0",
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["enrichment_count"], 1)
            retry_rows = read_jsonl(retry_snapshot_dir / "words.enriched.jsonl")
            self.assertEqual([row["entry_id"] for row in retry_rows], ["lx_run"])

        with tempfile.TemporaryDirectory() as skip_tmpdir:
            skip_snapshot_dir = Path(skip_tmpdir)
            self._write_resume_modes_snapshot(skip_snapshot_dir)
            write_jsonl(
                skip_snapshot_dir / "enrich.failures.jsonl",
                [{
                    "lexeme_id": "lx_run",
                    "entry_id": "lx_run",
                    "entry_type": "word",
                    "lemma": "run",
                    "display_form": "run",
                    "status": "failed",
                    "generation_run_id": "failed-run",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }],
            )

            code, stdout, stderr = self.run_cli_skip_guard([
                "enrich",
                "--snapshot-dir",
                str(skip_snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--resume",
                "--skip-failed",
                "--request-delay-seconds",
                "0",
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["enrichment_count"], 2)
            skip_rows = read_jsonl(skip_snapshot_dir / "words.enriched.jsonl")
            self.assertEqual({row["entry_id"] for row in skip_rows}, {"lx_alpha", "lx_play"})

    def test_staged_cli_placeholder_core_translation_merge_preserve_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            write_jsonl(snapshot_dir / "words.enriched.core.jsonl", [self._existing_alpha_core_row()])
            write_jsonl(snapshot_dir / "words.translations.jsonl", self._existing_alpha_translation_rows())

            code, stdout, stderr = self.run_cli_skip_guard([
                "enrich-core",
                "--snapshot-dir",
                str(snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--request-delay-seconds",
                "0",
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich-core")
            core_rows = read_jsonl(snapshot_dir / "words.enriched.core.jsonl")
            self.assertEqual({row["entry_id"] for row in core_rows}, {"lx_alpha", "lx_run", "lx_play"})
            self.assertEqual(sum(1 for row in core_rows if row["entry_id"] == "lx_alpha"), 1)
            self.assertEqual(
                {row["lexeme_id"] for row in read_jsonl(snapshot_dir / "enrich.core.checkpoint.jsonl")},
                {"lx_alpha", "lx_run", "lx_play"},
            )

            code, stdout, stderr = self.run_cli_skip_guard([
                "enrich-translations",
                "--snapshot-dir",
                str(snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "enrich-translations")
            translation_rows = read_jsonl(snapshot_dir / "words.translations.jsonl")
            self.assertEqual(len(translation_rows), 15)
            self.assertTrue(
                any(
                    row["entry_id"] == "lx_alpha"
                    and row["locale"] == "zh-Hans"
                    and row["definition"] == "zh:existing alpha"
                    for row in translation_rows
                )
            )
            self.assertEqual(
                {row["sense_id"] for row in read_jsonl(snapshot_dir / "enrich.translations.checkpoint.jsonl")},
                {"sn_lx_alpha_1", "sn_lx_run_1", "sn_lx_play_1"},
            )

            merged_output = snapshot_dir / "words.enriched.jsonl"
            code, stdout, stderr = self.run_cli_skip_guard([
                "merge-enrich",
                "--core-input",
                str(snapshot_dir / "words.enriched.core.jsonl"),
                "--translations-input",
                str(snapshot_dir / "words.translations.jsonl"),
                "--output",
                str(merged_output),
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "merge-enrich")
            merged_rows = read_jsonl(merged_output)
            self.assertEqual({row["entry_id"] for row in merged_rows}, {"lx_alpha", "lx_run", "lx_play"})
            alpha_row = next(row for row in merged_rows if row["entry_id"] == "lx_alpha")
            self.assertEqual(alpha_row["senses"][0]["translations"]["zh-Hans"]["definition"], "zh:existing alpha")

    def test_split_enrich_artifact_command_real_smoke_roundtrips_staged_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            self._write_single_snapshot(snapshot_dir)

            code, _, stderr = self.run_cli_skip_guard([
                "enrich",
                "--snapshot-dir",
                str(snapshot_dir),
                "--provider-mode",
                "placeholder",
                "--request-delay-seconds",
                "0",
                "--log-level",
                "quiet",
            ])
            self.assertEqual(code, 0, stderr)

            core_output = snapshot_dir / "words.enriched.core.jsonl"
            translations_output = snapshot_dir / "words.translations.jsonl"
            core_checkpoint = snapshot_dir / "enrich.core.checkpoint.jsonl"
            translations_checkpoint = snapshot_dir / "enrich.translations.checkpoint.jsonl"

            code, stdout, stderr = self.run_cli_skip_guard([
                "split-enrich-artifact",
                "--compiled-input",
                str(snapshot_dir / "words.enriched.jsonl"),
                "--core-output",
                str(core_output),
                "--translations-output",
                str(translations_output),
                "--core-checkpoint-path",
                str(core_checkpoint),
                "--translations-checkpoint-path",
                str(translations_checkpoint),
                "--log-level",
                "quiet",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "split-enrich-artifact")
            self.assertEqual(len(read_jsonl(core_output)), 1)
            self.assertEqual(len(read_jsonl(translations_output)), 5)
            self.assertEqual(len(read_jsonl(core_checkpoint)), 1)
            self.assertEqual(len(read_jsonl(translations_checkpoint)), 1)

    def test_runtime_guard_rejects_wrong_interpreter(self) -> None:
        with patch(
            "tools.lexicon.cli._ensure_lexicon_cli_runtime",
            side_effect=RuntimeError("Lexicon CLI must run with `.venv-lexicon/bin/python`."),
        ):
            code, _, stderr = self.run_cli([
                "enrich-core",
                "--snapshot-dir",
                "snapshot",
            ])

        self.assertEqual(code, 2)
        self.assertIn(".venv-lexicon/bin/python", stderr)

    def test_runtime_guard_bypass_survives_cleared_environment_under_pytest(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(cli._should_skip_lexicon_venv_guard())


if __name__ == "__main__":
    unittest.main()



    def test_review_materialize_command_writes_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            compiled_path = Path(tmpdir) / "compiled.jsonl"
            decisions_path = Path(tmpdir) / "review.decisions.jsonl"
            approved_path = Path(tmpdir) / "approved.jsonl"
            rejected_path = Path(tmpdir) / "rejected.jsonl"
            regenerate_path = Path(tmpdir) / "regenerate.jsonl"

            with patch(
                "tools.lexicon.cli.materialize_review_outputs",
                return_value={
                    "artifact_sha256": "a" * 64,
                    "decision_count": 2,
                    "approved_count": 1,
                    "rejected_count": 1,
                    "regenerate_count": 1,
                },
            ) as mocked_materialize:
                code, stdout, _ = self.run_cli([
                    "review-materialize",
                    "--compiled-input", str(compiled_path),
                    "--decisions-input", str(decisions_path),
                    "--approved-output", str(approved_path),
                    "--rejected-output", str(rejected_path),
                    "--regenerate-output", str(regenerate_path),
                ])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "review-materialize")
            self.assertEqual(payload["decision_count"], 2)
            self.assertEqual(payload["approved_count"], 1)
            self.assertEqual(payload["rejected_count"], 1)
            self.assertEqual(payload["regenerate_count"], 1)
            self.assertEqual(mocked_materialize.call_args.kwargs["compiled_path"], compiled_path)
            self.assertEqual(mocked_materialize.call_args.kwargs["decisions_input_path"], decisions_path)
            self.assertEqual(mocked_materialize.call_args.kwargs["approved_output_path"], approved_path)
            self.assertEqual(mocked_materialize.call_args.kwargs["rejected_output_path"], rejected_path)
            self.assertEqual(mocked_materialize.call_args.kwargs["regenerate_output_path"], regenerate_path)
