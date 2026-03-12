import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.lexicon import cli
from tools.lexicon.build_base import build_base_records


class FormAdjudicationTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_build_base_records_marks_ambiguous_surface_forms_for_llm(self) -> None:
        def rank_provider(word: str) -> int:
            return {"ringed": 1000, "ring": 1000}.get(word, 999_999)

        def sense_provider(word: str):
            if word == "ringed":
                return []
            if word == "ring":
                return [{
                    "wn_synset_id": "ring.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a circular band",
                    "canonical_label": "ring",
                }]
            return []

        result = build_base_records(
            words=["ringed"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
        )

        self.assertEqual(len(result.ambiguous_forms), 1)
        row = result.ambiguous_forms[0]
        self.assertEqual(row.surface_form, "ringed")
        self.assertEqual(row.deterministic_decision, "unknown_needs_llm")
        self.assertIn("ring", row.candidate_forms)

    def test_build_base_records_applies_adjudication_overrides(self) -> None:
        def rank_provider(word: str) -> int:
            return {"ringed": 1000, "ring": 1000}.get(word, 999_999)

        def sense_provider(word: str):
            if word == "ring":
                return [{
                    "wn_synset_id": "ring.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a circular band",
                    "canonical_label": "ring",
                }]
            return []

        adjudications = {
            "ringed": {
                "selected_action": "collapse_to_canonical",
                "selected_canonical_form": "ring",
                "selected_linked_canonical_form": None,
            }
        }

        result = build_base_records(
            words=["ringed"],
            snapshot_id="lexicon-20260312-wordnet-wordfreq",
            created_at="2026-03-12T00:00:00Z",
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            adjudications=adjudications,
        )

        self.assertEqual([record.lemma for record in result.lexemes], ["ring"])
        self.assertEqual(result.canonical_variants[0].decision, "collapse_to_canonical")
        self.assertEqual(result.canonical_variants[0].canonical_form, "ring")

    def test_detect_ambiguous_forms_cli_writes_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "ambiguous_forms.jsonl"
            with patch("tools.lexicon.cli._load_build_base_providers") as mocked_providers:
                def rank_provider(word: str) -> int:
                    return {"ringed": 1000, "ring": 1000}.get(word, 999_999)

                def sense_provider(word: str):
                    return []

                mocked_providers.return_value = (rank_provider, sense_provider)
                code, stdout, stderr = self.run_cli([
                    "detect-ambiguous-forms",
                    "--output",
                    str(output_path),
                    "ringed",
                ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "detect-ambiguous-forms")
            self.assertEqual(payload["ambiguous_count"], 1)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["surface_form"], "ringed")

    def test_adjudicate_forms_cli_placeholder_writes_bounded_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "ambiguous_forms.jsonl"
            output_path = Path(tmpdir) / "form_adjudications.jsonl"
            input_path.write_text(
                json.dumps(
                    {
                        "surface_form": "close",
                        "deterministic_decision": "unknown_needs_llm",
                        "canonical_form": "close",
                        "linked_canonical_form": None,
                        "candidate_forms": ["conclude", "near"],
                        "decision_reason": "deterministic signals found candidate forms but no strong canonical winner",
                        "confidence": 0.45,
                        "wordfreq_rank": 431,
                        "sense_labels": ["close", "conclude", "near"],
                        "ambiguity_reason": "candidate set exists but deterministic score stayed below the collapse threshold",
                    }
                ) + "\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli([
                "adjudicate-forms",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--provider-mode",
                "placeholder",
            ])

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "adjudicate-forms")
            self.assertEqual(payload["adjudication_count"], 1)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["surface_form"], "close")
            self.assertEqual(rows[0]["selected_action"], "collapse_to_canonical")
            self.assertEqual(rows[0]["selected_canonical_form"], "conclude")
            self.assertEqual(rows[0]["candidate_forms"], ["conclude", "near"])

    def test_validate_adjudication_rejects_invented_canonical_form(self) -> None:
        from tools.lexicon.form_adjudication import validate_adjudication_row

        with self.assertRaisesRegex(RuntimeError, "must be the surface form or one of the candidate_forms"):
            validate_adjudication_row(
                {
                    "surface_form": "ringed",
                    "candidate_forms": ["ring", "ringe"],
                    "selected_action": "collapse_to_canonical",
                    "selected_canonical_form": "invented",
                    "selected_linked_canonical_form": None,
                    "confidence": 0.8,
                }
            )


if __name__ == "__main__":
    unittest.main()
