from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.batch_prepare import build_batch_request_rows, write_batch_request_rows


class BatchPrepareTests(unittest.TestCase):
    def test_build_batch_request_rows_is_deterministic_and_kind_aware(self) -> None:
        rows = build_batch_request_rows(
            snapshot_id="lexicon-20260320-seeds",
            model="gpt-5-mini",
            prompt_version="v1",
            rows=[
                {"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"},
                {"entry_kind": "phrase", "entry_id": "ph_take_off", "display_form": "take off"},
            ],
        )

        self.assertEqual(rows[0]["custom_id"], "reference:lexicon-20260320-seeds:rf_melbourne:attempt1")
        self.assertEqual(rows[1]["custom_id"], "phrase:lexicon-20260320-seeds:ph_take_off:attempt1")
        self.assertEqual(rows[0]["body"]["entry_kind"], "reference")
        self.assertEqual(rows[1]["body"]["entry_kind"], "phrase")

    def test_write_batch_request_rows_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "batch_requests.jsonl"
            rows = build_batch_request_rows(
                snapshot_id="lexicon-20260320-seeds",
                model="gpt-5-mini",
                prompt_version="v1",
                rows=[
                    {"entry_kind": "reference", "entry_id": "rf_melbourne", "display_form": "Melbourne"},
                ],
            )

            written = write_batch_request_rows(output_path, rows)

            self.assertEqual(written, output_path)
            payload = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["custom_id"], "reference:lexicon-20260320-seeds:rf_melbourne:attempt1")

