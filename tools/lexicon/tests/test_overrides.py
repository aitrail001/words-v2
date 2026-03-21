from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.overrides import apply_manual_overrides, load_manual_overrides


class OverrideTests(unittest.TestCase):
    def test_load_manual_overrides_accepts_custom_id_and_entry_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "overrides.jsonl"
            write_jsonl(
                path,
                [
                    {"custom_id": "word:demo:sn_run_1:attempt1", "verdict": "pass", "review_notes": "known good"},
                    {"entry_id": "sn_walk_1", "verdict": "fail", "review_notes": "reject"},
                ],
            )

            overrides = load_manual_overrides(path)

            self.assertEqual(overrides["word:demo:sn_run_1:attempt1"]["verdict"], "pass")
            self.assertEqual(overrides["sn_walk_1"]["review_notes"], "reject")

    def test_apply_manual_overrides_updates_matching_rows_without_touching_others(self) -> None:
        rows = [
            {"custom_id": "word:demo:sn_run_1:attempt1", "entry_id": "sn_run_1", "verdict": "needs_review", "confidence": 0.8},
            {"custom_id": "word:demo:sn_walk_1:attempt1", "entry_id": "sn_walk_1", "verdict": "fail", "confidence": 0.2},
        ]
        overrides = {
            "word:demo:sn_run_1:attempt1": {
                "custom_id": "word:demo:sn_run_1:attempt1",
                "verdict": "pass",
                "confidence": 0.99,
                "review_notes": "approved by reviewer",
                "reasons": ["override"],
                "model_name": None,
                "prompt_version": None,
            }
        }

        updated = apply_manual_overrides(rows, overrides)

        self.assertEqual(updated[0]["verdict"], "pass")
        self.assertEqual(updated[0]["confidence"], 0.99)
        self.assertTrue(updated[0]["override_applied"])
        self.assertEqual(updated[0]["review_notes"], "approved by reviewer")
        self.assertEqual(updated[1]["verdict"], "fail")
