from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon import cli
from tools.lexicon.batch_ingest import build_batch_result_rows
from tools.lexicon.batch_prepare import build_batch_request_rows
from tools.lexicon.qc import build_qc_verdict_rows, build_review_queue_rows


class BatchLifecycleTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = []
        stderr = []
        import io
        from contextlib import redirect_stdout, redirect_stderr

        out_buffer = io.StringIO()
        err_buffer = io.StringIO()
        with redirect_stdout(out_buffer), redirect_stderr(err_buffer):
            try:
                code = cli.main(argv)
            except SystemExit as exc:  # pragma: no cover - argparse failure path
                code = int(exc.code)
        return code, out_buffer.getvalue(), err_buffer.getvalue()

    def test_build_batch_result_rows_matches_out_of_order_outputs(self) -> None:
        request_rows = build_batch_request_rows(
            snapshot_id="lexicon-20260320-seeds",
            model="gpt-5-mini",
            prompt_version="v1",
            rows=[
                {"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"},
                {"entry_kind": "phrase", "entry_id": "ph_take_off", "display_form": "take off"},
            ],
        )
        output_rows = [
            {"custom_id": request_rows[1]["custom_id"], "response": {"body": {"ok": True}}},
            {"custom_id": request_rows[0]["custom_id"], "error": {"class": "validation_error", "message": "bad payload"}},
        ]

        results = build_batch_result_rows(request_rows=request_rows, output_rows=output_rows, ingested_at="2026-03-20T00:00:00Z")

        self.assertEqual(results[0]["status"], "accepted")
        self.assertEqual(results[1]["status"], "failed")
        self.assertEqual(results[0]["qc_status"], "pending")
        self.assertEqual(results[1]["qc_status"], "needs_review")

    def test_qc_helpers_apply_overrides_and_build_review_queue(self) -> None:
        rows = [
            {"custom_id": "reference:lexicon:s1:attempt1", "entry_kind": "reference", "entry_id": "s1", "status": "accepted", "validation_status": "valid", "error_detail": None},
            {"custom_id": "phrase:lexicon:s2:attempt1", "entry_kind": "phrase", "entry_id": "s2", "status": "failed", "validation_status": "invalid", "error_detail": "bad payload"},
        ]

        verdict_rows = build_qc_verdict_rows(
            result_rows=rows,
            reviewed_at="2026-03-20T00:00:00Z",
            overrides={"phrase:lexicon:s2:attempt1": {"custom_id": "phrase:lexicon:s2:attempt1", "verdict": "pass", "confidence": 0.75}},
        )
        review_queue_rows = build_review_queue_rows(verdict_rows)

        self.assertEqual(verdict_rows[0]["verdict"], "pass")
        self.assertEqual(verdict_rows[1]["verdict"], "pass")
        self.assertEqual(verdict_rows[1]["override_applied"], True)
        self.assertEqual(verdict_rows[0]["review_priority"], 100)
        self.assertEqual(verdict_rows[1]["review_priority"], 100)
        self.assertEqual(review_queue_rows, [])

    def test_cli_batch_lifecycle_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            snapshot_dir = root / "snapshot"
            snapshot_dir.mkdir()
            request_rows = build_batch_request_rows(
                snapshot_id="lexicon-20260320-seeds",
                model="gpt-5-mini",
                prompt_version="v1",
                rows=[
                    {"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"},
                    {"entry_kind": "phrase", "entry_id": "ph_take_off", "display_form": "take off"},
                ],
            )
            (snapshot_dir / "batch_requests.jsonl").write_text(
                "\n".join(json.dumps(row) for row in request_rows) + "\n",
                encoding="utf-8",
            )
            output_path = root / "batch_output.jsonl"
            output_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "custom_id": request_rows[1]["custom_id"],
                                "response": {
                                    "body": {
                                        "output": [
                                            {
                                                "type": "message",
                                                "content": [
                                                    {
                                                        "type": "output_text",
                                                        "text": json.dumps(
                                                            {
                                                                "phrase_kind": "multiword_expression",
                                                                "confidence": 0.8,
                                                                "senses": [
                                                                    {
                                                                        "definition": "to leave the ground suddenly",
                                                                        "part_of_speech": "phrase",
                                                                        "examples": [
                                                                            {
                                                                                "sentence": "The plane will take off soon.",
                                                                                "difficulty": "B1",
                                                                            }
                                                                        ],
                                                                        "grammar_patterns": ["subject + take off"],
                                                                        "usage_note": "Common travel phrase.",
                                                                        "translations": {
                                                                            "es": {
                                                                                "definition": "despegar",
                                                                                "examples": ["The plane will take off soon."],
                                                                                "usage_note": "Common travel phrase.",
                                                                            },
                                                                            "zh-Hans": {
                                                                                "definition": "起飞",
                                                                                "examples": ["The plane will take off soon."],
                                                                                "usage_note": "Common travel phrase.",
                                                                            },
                                                                            "ar": {
                                                                                "definition": "يقلع",
                                                                                "examples": ["The plane will take off soon."],
                                                                                "usage_note": "Common travel phrase.",
                                                                            },
                                                                            "pt-BR": {
                                                                                "definition": "decolar",
                                                                                "examples": ["The plane will take off soon."],
                                                                                "usage_note": "Common travel phrase.",
                                                                            },
                                                                            "ja": {
                                                                                "definition": "離陸する",
                                                                                "examples": ["The plane will take off soon."],
                                                                                "usage_note": "Common travel phrase.",
                                                                            },
                                                                        },
                                                                    }
                                                                ],
                                                            }
                                                        ),
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                },
                            }
                        ),
                        json.dumps({"custom_id": request_rows[0]["custom_id"], "error": {"class": "validation_error", "message": "bad payload"}}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            overrides_path = root / "manual_overrides.jsonl"
            overrides_path.write_text(
                json.dumps({"custom_id": request_rows[0]["custom_id"], "verdict": "pass", "confidence": 0.9}) + "\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli(["batch-submit", "--snapshot-dir", str(snapshot_dir)])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            submit_payload = json.loads(stdout)
            self.assertEqual(submit_payload["command"], "batch-submit")
            self.assertEqual(submit_payload["job_count"], 2)
            self.assertTrue((snapshot_dir / "batch_jobs.jsonl").exists())

            code, stdout, stderr = self.run_cli(["batch-ingest", "--snapshot-dir", str(snapshot_dir), "--input", str(output_path)])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            ingest_payload = json.loads(stdout)
            self.assertEqual(ingest_payload["command"], "batch-ingest")
            self.assertEqual(ingest_payload["result_count"], 2)
            self.assertTrue((snapshot_dir / "batch_results.jsonl").exists())

            code, stdout, stderr = self.run_cli(["batch-status", "--snapshot-dir", str(snapshot_dir)])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            status_payload = json.loads(stdout)
            self.assertEqual(status_payload["jobs"]["total"], 2)
            self.assertEqual(status_payload["results"]["total"], 2)
            self.assertEqual(status_payload["results"]["accepted"], 1)
            self.assertEqual(status_payload["results"]["failed"], 1)

            code, stdout, stderr = self.run_cli(["batch-retry", "--snapshot-dir", str(snapshot_dir), "--results", str(snapshot_dir / "batch_results.jsonl"), "--model", "gpt-5-mini", "--prompt-version", "v1"])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            retry_payload = json.loads(stdout)
            self.assertEqual(retry_payload["command"], "batch-retry")
            self.assertEqual(retry_payload["retry_count"], 1)
            self.assertTrue((snapshot_dir / "batch_requests.retry.jsonl").exists())

            code, stdout, stderr = self.run_cli([
                "batch-qc",
                "--snapshot-dir",
                str(snapshot_dir),
                "--results",
                str(snapshot_dir / "batch_results.jsonl"),
                "--overrides",
                str(overrides_path),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            qc_payload = json.loads(stdout)
            self.assertEqual(qc_payload["command"], "batch-qc")
            self.assertEqual(qc_payload["verdict_count"], 2)
            self.assertEqual(qc_payload["review_queue_count"], 0)
            self.assertTrue((snapshot_dir / "batch_qc.jsonl").exists())
            self.assertTrue((snapshot_dir / "enrichment_review_queue.jsonl").exists())
