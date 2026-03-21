from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.batch_ingest import build_batch_result_rows, ingest_batch_outputs
from tools.lexicon.batch_prepare import build_batch_request_rows
from tools.lexicon.jsonl_io import write_jsonl


class BatchIngestTests(unittest.TestCase):
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

    def test_ingest_batch_outputs_appends_accepted_rows_and_records_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            request_rows = build_batch_request_rows(
                snapshot_id="lexicon-20260320-seeds",
                model="gpt-5-mini",
                prompt_version="v1",
                rows=[
                    {"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"},
                    {"entry_kind": "phrase", "entry_id": "ph_take_off", "display_form": "take off"},
                ],
            )
            write_jsonl(snapshot_dir / "batch_requests.jsonl", request_rows)

            existing_results = [
                {"custom_id": "reference:lexicon-20260320-seeds:rf_existing:attempt1", "status": "accepted", "validation_status": "valid", "qc_status": "pending", "attempt": 1},
            ]
            write_jsonl(snapshot_dir / "batch_results.jsonl", existing_results)

            output_path = snapshot_dir / "batch_output.jsonl"
            write_jsonl(
                output_path,
                [
                    {"custom_id": request_rows[1]["custom_id"], "response": {"body": {"ok": True}}},
                    {"custom_id": request_rows[0]["custom_id"], "error": {"class": "validation_error", "message": "bad payload"}},
                ],
            )

            result_rows = ingest_batch_outputs(
                snapshot_dir=snapshot_dir,
                output_path=snapshot_dir / "batch_results.jsonl",
                request_path=snapshot_dir / "batch_requests.jsonl",
                batch_output_path=output_path,
                ingested_at="2026-03-20T00:00:00Z",
                failure_output_path=snapshot_dir / "batch_failures.jsonl",
            )

            persisted_results = [json.loads(line) for line in (snapshot_dir / "batch_results.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            failures = [json.loads(line) for line in (snapshot_dir / "batch_failures.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(len(result_rows), 2)
            self.assertEqual(len(persisted_results), 3)
            self.assertEqual(persisted_results[0]["custom_id"], "reference:lexicon-20260320-seeds:rf_existing:attempt1")
            self.assertEqual(persisted_results[1]["custom_id"], request_rows[1]["custom_id"])
            self.assertEqual(persisted_results[2]["custom_id"], request_rows[0]["custom_id"])
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["custom_id"], request_rows[0]["custom_id"])
