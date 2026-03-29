import tempfile
import unittest
from pathlib import Path

from tools.lexicon.voice_generate import plan_voice_work_units, run_voice_generation


class FakeSynthProvider:
    def __init__(self, failing_unit_id: str | None = None) -> None:
        self.failing_unit_id = failing_unit_id

    def synthesize(self, unit, output_path: Path) -> None:
        if self.failing_unit_id == unit.unit_id:
            raise RuntimeError("boom")
        output_path.write_bytes(f"{unit.locale}:{unit.voice_role}:{unit.content_scope}".encode("utf-8"))


class VoiceGenerateTests(unittest.TestCase):
    def test_plan_voice_work_units_expands_word_definition_and_example_across_locales_and_roles(self) -> None:
        rows = [
            {
                "entry_id": "word_bank",
                "entry_type": "word",
                "word": "bank",
                "language": "en",
                "source_reference": "snapshot-001",
                "senses": [
                    {
                        "sense_id": "bank.n.01",
                        "definition": "a financial institution",
                        "examples": [{"sentence": "She went to the bank."}],
                    }
                ],
            }
        ]

        units = plan_voice_work_units(
            rows,
            provider="google",
            family="neural2",
            locales=["en-US", "en-GB"],
            audio_format="mp3",
            storage_kind="local",
            storage_base="/tmp/voice",
        )

        self.assertEqual(len(units), 12)
        us_female_word = next(unit for unit in units if unit.content_scope == "word" and unit.locale == "en-US" and unit.voice_role == "female")
        uk_male_definition = next(unit for unit in units if unit.content_scope == "definition" and unit.locale == "en-GB" and unit.voice_role == "male")
        self.assertEqual(us_female_word.voice_id, "en-US-Neural2-C")
        self.assertEqual(uk_male_definition.voice_id, "en-GB-Neural2-B")
        self.assertIn("word_bank/word/en_us", us_female_word.relative_path)

    def test_run_voice_generation_writes_manifest_and_errors_without_stopping(self) -> None:
        approved_jsonl = """{"entry_id":"word_bank","entry_type":"word","word":"bank","language":"en","source_reference":"snapshot-001","senses":[{"sense_id":"bank.n.01","definition":"a financial institution","examples":[{"sentence":"She went to the bank."}]}]}\n"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "approved.jsonl"
            output_dir = Path(tmpdir) / "voice"
            input_path.write_text(approved_jsonl, encoding="utf-8")
            planned_units = plan_voice_work_units(
                [
                    {
                        "entry_id": "word_bank",
                        "entry_type": "word",
                        "word": "bank",
                        "language": "en",
                        "source_reference": "snapshot-001",
                        "senses": [{"sense_id": "bank.n.01", "definition": "a financial institution", "examples": [{"sentence": "She went to the bank."}]}],
                    }
                ],
                provider="google",
                family="neural2",
                locales=["en-US"],
                audio_format="mp3",
                storage_kind="local",
                storage_base=str(output_dir),
            )
            failing_unit_id = planned_units[0].unit_id

            summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=2,
                synth_provider=FakeSynthProvider(failing_unit_id=failing_unit_id),
            )

            self.assertEqual(summary["planned_count"], 6)
            self.assertEqual(summary["failed_count"], 1)
            manifest_lines = (output_dir / "voice_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
            error_lines = (output_dir / "voice_errors.jsonl").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(manifest_lines), 5)
            self.assertEqual(len(error_lines), 1)
            self.assertTrue((output_dir / planned_units[1].relative_path).exists())

    def test_run_voice_generation_resume_skips_units_recorded_in_manifest_even_if_file_is_missing(self) -> None:
        approved_jsonl = """{"entry_id":"word_bank","entry_type":"word","word":"bank","language":"en","source_reference":"snapshot-001","senses":[{"sense_id":"bank.n.01","definition":"a financial institution","examples":[{"sentence":"She went to the bank."}]}]}\n"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "approved.jsonl"
            output_dir = Path(tmpdir) / "voice"
            input_path.write_text(approved_jsonl, encoding="utf-8")

            first_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                synth_provider=FakeSynthProvider(),
            )
            self.assertEqual(first_summary["generated_count"], 6)

            manifest_path = output_dir / "voice_manifest.jsonl"
            manifest_lines = manifest_path.read_text(encoding="utf-8").strip().splitlines()
            first_line = manifest_lines[0]
            first_relative_path = first_line.split('"relative_path": "')[1].split('"', 1)[0]
            (output_dir / first_relative_path).unlink()

            resumed_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                resume=True,
                synth_provider=FakeSynthProvider(),
            )

            self.assertEqual(resumed_summary["planned_count"], 6)
            self.assertEqual(resumed_summary["generated_count"], 0)
            self.assertEqual(resumed_summary["existing_count"], 0)
            self.assertEqual(resumed_summary["skipped_completed_count"], 6)
            self.assertFalse((output_dir / first_relative_path).exists())

    def test_run_voice_generation_resume_retries_failed_units_only(self) -> None:
        approved_jsonl = """{"entry_id":"word_bank","entry_type":"word","word":"bank","language":"en","source_reference":"snapshot-001","senses":[{"sense_id":"bank.n.01","definition":"a financial institution","examples":[{"sentence":"She went to the bank."}]}]}\n"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "approved.jsonl"
            output_dir = Path(tmpdir) / "voice"
            input_path.write_text(approved_jsonl, encoding="utf-8")
            planned_units = plan_voice_work_units(
                [
                    {
                        "entry_id": "word_bank",
                        "entry_type": "word",
                        "word": "bank",
                        "language": "en",
                        "source_reference": "snapshot-001",
                        "senses": [{"sense_id": "bank.n.01", "definition": "a financial institution", "examples": [{"sentence": "She went to the bank."}]}],
                    }
                ],
                provider="google",
                family="neural2",
                locales=["en-US"],
                audio_format="mp3",
                storage_kind="local",
                storage_base=str(output_dir),
            )

            first_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                synth_provider=FakeSynthProvider(failing_unit_id=planned_units[0].unit_id),
            )
            self.assertEqual(first_summary["failed_count"], 1)

            resumed_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                resume=True,
                retry_failed_only=True,
                synth_provider=FakeSynthProvider(),
            )

            self.assertEqual(resumed_summary["planned_count"], 6)
            self.assertEqual(resumed_summary["generated_count"], 1)
            self.assertEqual(resumed_summary["failed_count"], 0)
            self.assertEqual(resumed_summary["skipped_completed_count"], 5)
            self.assertEqual(resumed_summary["retried_failed_count"], 1)

    def test_run_voice_generation_resume_can_skip_prior_failed_units(self) -> None:
        approved_jsonl = """{"entry_id":"word_bank","entry_type":"word","word":"bank","language":"en","source_reference":"snapshot-001","senses":[{"sense_id":"bank.n.01","definition":"a financial institution","examples":[{"sentence":"She went to the bank."}]}]}\n"""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "approved.jsonl"
            output_dir = Path(tmpdir) / "voice"
            input_path.write_text(approved_jsonl, encoding="utf-8")
            planned_units = plan_voice_work_units(
                [
                    {
                        "entry_id": "word_bank",
                        "entry_type": "word",
                        "word": "bank",
                        "language": "en",
                        "source_reference": "snapshot-001",
                        "senses": [{"sense_id": "bank.n.01", "definition": "a financial institution", "examples": [{"sentence": "She went to the bank."}]}],
                    }
                ],
                provider="google",
                family="neural2",
                locales=["en-US"],
                audio_format="mp3",
                storage_kind="local",
                storage_base=str(output_dir),
            )

            first_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                synth_provider=FakeSynthProvider(failing_unit_id=planned_units[0].unit_id),
            )
            self.assertEqual(first_summary["failed_count"], 1)

            resumed_summary = run_voice_generation(
                input_path=input_path,
                output_dir=output_dir,
                locales=["en-US"],
                max_concurrency=1,
                resume=True,
                skip_failed=True,
                synth_provider=FakeSynthProvider(),
            )

            self.assertEqual(resumed_summary["planned_count"], 6)
            self.assertEqual(resumed_summary["scheduled_count"], 0)
            self.assertEqual(resumed_summary["generated_count"], 0)
            self.assertEqual(resumed_summary["skipped_completed_count"], 5)
            self.assertEqual(resumed_summary["skipped_failed_count"], 1)
