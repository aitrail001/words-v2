from __future__ import annotations

import unittest
from pathlib import Path

from tools.lexicon.batch_ledger import BatchArtifactPaths, build_batch_custom_id, parse_batch_custom_id


class BatchLedgerTests(unittest.TestCase):
    def test_batch_custom_id_round_trips(self) -> None:
        custom_id = build_batch_custom_id(
            entry_kind="reference",
            snapshot_id="lexicon-20260320-reference-seeds",
            entry_id="rf_melbourne",
            attempt=2,
        )

        parsed = parse_batch_custom_id(custom_id)

        self.assertEqual(parsed["entry_kind"], "reference")
        self.assertEqual(parsed["snapshot_id"], "lexicon-20260320-reference-seeds")
        self.assertEqual(parsed["entry_id"], "rf_melbourne")
        self.assertEqual(parsed["attempt"], 2)

    def test_batch_artifact_paths_are_under_snapshot_dir(self) -> None:
        paths = BatchArtifactPaths.from_snapshot_dir(Path("/tmp/lexicon-snapshot"))

        self.assertEqual(paths.snapshot_dir, Path("/tmp/lexicon-snapshot"))
        self.assertEqual(paths.batch_requests_path, Path("/tmp/lexicon-snapshot") / "batch_requests.jsonl")
        self.assertEqual(paths.batch_jobs_path, Path("/tmp/lexicon-snapshot") / "batch_jobs.jsonl")
        self.assertEqual(paths.batch_inputs_dir, Path("/tmp/lexicon-snapshot") / "batches")

