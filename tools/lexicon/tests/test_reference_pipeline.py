from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.reference_pipeline import build_reference_snapshot_rows, write_reference_snapshot


class ReferencePipelineTests(unittest.TestCase):
    def test_build_reference_snapshot_rows_normalizes_and_dedupes(self) -> None:
        rows = build_reference_snapshot_rows(
            references=[
                {
                    "display_form": " Melbourne ",
                    "reference_type": "place",
                    "translation_mode": "localized_display",
                    "brief_description": " A major city in Australia. ",
                    "pronunciation": " MEL-burn ",
                },
                {
                    "display_form": "Melbourne",
                    "reference_type": "place",
                    "translation_mode": "localized_display",
                    "brief_description": "Duplicate row",
                    "pronunciation": "MEL-burn",
                },
            ],
            snapshot_id="reference-snap-1",
            created_at="2026-03-20T00:00:00Z",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["entry_kind"], "reference")
        self.assertEqual(rows[0]["entry_type"], "reference")
        self.assertEqual(rows[0]["normalized_form"], "melbourne")
        self.assertEqual(rows[0]["reference_type"], "place")
        self.assertEqual(rows[0]["translation_mode"], "localized_display")
        self.assertTrue(rows[0]["entry_id"].startswith("rf_"))

    def test_write_reference_snapshot_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            rows = build_reference_snapshot_rows(
                references=[
                    {
                        "display_form": "RSVP",
                        "reference_type": "abbreviation",
                        "translation_mode": "keep_original",
                        "brief_description": "An invitation response abbreviation.",
                        "pronunciation": "ar-es-vee-pee",
                    }
                ],
                snapshot_id="reference-snap-1",
                created_at="2026-03-20T00:00:00Z",
            )

            output_path = write_reference_snapshot(output_dir, rows)

            self.assertEqual(output_path, output_dir / "references.jsonl")
            payload = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["display_form"], "RSVP")
