from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.phrase_pipeline import build_phrase_snapshot_rows, write_phrase_snapshot


class PhrasePipelineTests(unittest.TestCase):
    def test_build_phrase_snapshot_rows_normalizes_and_dedupes(self) -> None:
        rows = build_phrase_snapshot_rows(
            phrases=[
                {
                    "phrase": " Take off ",
                    "phrase_kind": "phrasal_verb",
                    "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
                },
                {"phrase": "take off", "phrase_kind": "phrasal_verb"},
                {
                    "phrase": "on and off",
                    "phrase_kind": "multiword_expression",
                    "source_provenance": [{"source": "reviewed_idioms.csv", "raw_reviewed_as": "fixed phrase"}],
                    "seed_metadata": {"raw_reviewed_as": "fixed phrase"},
                },
            ],
            snapshot_id="phrase-snap-1",
            created_at="2026-03-20T00:00:00Z",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["entry_kind"], "phrase")
        self.assertEqual(rows[0]["entry_type"], "phrase")
        self.assertEqual(rows[0]["normalized_form"], "take off")
        self.assertEqual(rows[0]["phrase_kind"], "phrasal_verb")
        self.assertEqual(rows[0]["seed_metadata"]["raw_reviewed_as"], "phrasal verb")
        self.assertTrue(rows[0]["entry_id"].startswith("ph_"))
        self.assertEqual(rows[1]["source_provenance"][0]["raw_reviewed_as"], "fixed phrase")

    def test_write_phrase_snapshot_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            rows = build_phrase_snapshot_rows(
                phrases=[{"phrase": "Take off", "phrase_kind": "phrasal_verb"}],
                snapshot_id="phrase-snap-1",
                created_at="2026-03-20T00:00:00Z",
            )

            output_path = write_phrase_snapshot(output_dir, rows)

            self.assertEqual(output_path, output_dir / "phrases.jsonl")
            payload = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["display_form"], "Take off")
