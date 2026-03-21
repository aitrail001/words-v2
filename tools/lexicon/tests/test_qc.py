from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.qc import build_qc_verdict_rows, build_review_queue_rows, run_batch_qc, run_review_apply


class QCTests(unittest.TestCase):
    def test_build_qc_verdict_rows_and_review_queue(self) -> None:
        rows = [
            {"custom_id": "reference:lexicon:s1:attempt1", "entry_kind": "reference", "entry_id": "s1", "status": "accepted", "validation_status": "valid", "error_detail": None},
            {"custom_id": "phrase:lexicon:s2:attempt1", "entry_kind": "phrase", "entry_id": "s2", "status": "failed", "validation_status": "invalid", "error_detail": "bad payload"},
        ]

        verdict_rows = build_qc_verdict_rows(
            result_rows=rows,
            reviewed_at="2026-03-20T00:00:00Z",
        )
        review_queue_rows = build_review_queue_rows(verdict_rows)

        self.assertEqual(verdict_rows[0]["verdict"], "pass")
        self.assertEqual(verdict_rows[1]["verdict"], "fail")
        self.assertEqual(review_queue_rows[0]["custom_id"], "phrase:lexicon:s2:attempt1")

    def test_run_batch_qc_applies_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            write_jsonl(
                snapshot_dir / "batch_results.jsonl",
                [
                    {"custom_id": "reference:lexicon:s1:attempt1", "entry_kind": "reference", "entry_id": "s1", "status": "accepted", "validation_status": "valid", "error_detail": None},
                    {"custom_id": "phrase:lexicon:s2:attempt1", "entry_kind": "phrase", "entry_id": "s2", "status": "failed", "validation_status": "invalid", "error_detail": "bad payload"},
                ],
            )
            write_jsonl(
                snapshot_dir / "manual_overrides.jsonl",
                [
                    {"custom_id": "phrase:lexicon:s2:attempt1", "verdict": "pass", "confidence": 0.9, "review_notes": "approved"},
                ],
            )

            verdict_rows, review_queue_rows = run_batch_qc(
                snapshot_dir=snapshot_dir,
                overrides_path=snapshot_dir / "manual_overrides.jsonl",
                reviewed_at="2026-03-20T00:00:00Z",
            )

            persisted = [json.loads(line) for line in (snapshot_dir / "batch_qc.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(verdict_rows[1]["verdict"], "pass")
            self.assertTrue(verdict_rows[1]["override_applied"])
            self.assertEqual(review_queue_rows, [])
            self.assertEqual(persisted[1]["review_notes"], "approved")

    def test_run_review_apply_updates_existing_qc_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            write_jsonl(
                snapshot_dir / "batch_qc.jsonl",
                [
                    {"custom_id": "reference:lexicon:s1:attempt1", "entry_kind": "reference", "entry_id": "s1", "verdict": "fail", "confidence": 0.0, "reasons": ["status=failed"], "review_notes": "bad payload", "model_name": "gpt-5-mini", "prompt_version": "v1", "reviewed_at": "2026-03-20T00:00:00Z"},
                    {"custom_id": "phrase:lexicon:s2:attempt1", "entry_kind": "phrase", "entry_id": "s2", "verdict": "pass", "confidence": 1.0, "reasons": [], "review_notes": None, "model_name": "gpt-5-mini", "prompt_version": "v1", "reviewed_at": "2026-03-20T00:00:00Z"},
                ],
            )
            write_jsonl(
                snapshot_dir / "manual_overrides.jsonl",
                [
                    {"custom_id": "reference:lexicon:s1:attempt1", "verdict": "pass", "confidence": 0.95, "review_notes": "approved"},
                ],
            )

            verdict_rows, review_queue_rows = run_review_apply(
                snapshot_dir=snapshot_dir,
                overrides_path=snapshot_dir / "manual_overrides.jsonl",
            )

            persisted = [json.loads(line) for line in (snapshot_dir / "batch_qc.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(verdict_rows[0]["verdict"], "pass")
            self.assertTrue(verdict_rows[0]["override_applied"])
            self.assertEqual(persisted[0]["review_notes"], "approved")
            self.assertEqual(review_queue_rows, [])
