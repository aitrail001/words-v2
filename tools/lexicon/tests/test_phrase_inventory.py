from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.phrase_inventory import build_phrase_inventory_records


class PhraseInventoryTests(unittest.TestCase):
    def _write_csv(self, path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = [
            "expression",
            "original_order",
            "source",
            "reviewed_as",
            "difficulty",
            "commonality",
            "added",
            "confidence",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_build_phrase_inventory_records_maps_labels_and_preserves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            phrasals_csv = root / "reviewed_phrasal_verbs.csv"
            idioms_csv = root / "reviewed_idioms.csv"
            self._write_csv(
                phrasals_csv,
                [
                    {
                        "expression": "Take Off",
                        "original_order": "1",
                        "source": "curated_phrasals",
                        "reviewed_as": "phrasal verb",
                        "difficulty": "B1",
                        "commonality": "high",
                        "added": "yes",
                        "confidence": "0.92",
                    }
                ],
            )
            self._write_csv(
                idioms_csv,
                [
                    {
                        "expression": "Break a leg",
                        "original_order": "7",
                        "source": "curated_idioms",
                        "reviewed_as": "idiom",
                        "difficulty": "B2",
                        "commonality": "medium",
                        "added": "no",
                        "confidence": "0.88",
                    },
                    {
                        "expression": "As a rule",
                        "original_order": "8",
                        "source": "curated_idioms",
                        "reviewed_as": "fixed phrase",
                        "difficulty": "B1",
                        "commonality": "high",
                        "added": "yes",
                        "confidence": "0.8",
                    },
                ],
            )

            records = build_phrase_inventory_records([phrasals_csv, idioms_csv])

        self.assertEqual([record["normalized_form"] for record in records], ["take off", "break a leg", "as a rule"])
        self.assertEqual(records[0]["phrase_kind"], "phrasal_verb")
        self.assertEqual(records[1]["phrase_kind"], "idiom")
        self.assertEqual(records[2]["phrase_kind"], "multiword_expression")
        self.assertEqual(records[0]["source_provenance"][0]["raw_reviewed_as"], "phrasal verb")
        self.assertEqual(records[1]["source_provenance"][0]["source_file"], str(idioms_csv))
        self.assertEqual(records[2]["seed_metadata"]["raw_reviewed_as"], "fixed phrase")
        self.assertEqual(records[0]["seed_metadata"]["review_confidence"], 0.92)
        self.assertEqual(records[2]["seed_metadata"]["source_order"], 8)

    def test_build_phrase_inventory_records_dedupes_normalized_forms_and_merges_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_a = root / "reviewed_a.csv"
            source_b = root / "reviewed_b.csv"
            self._write_csv(
                source_a,
                [
                    {
                        "expression": "Take off",
                        "original_order": "1",
                        "source": "source_a",
                        "reviewed_as": "phrasal verb",
                        "difficulty": "B1",
                        "commonality": "high",
                        "added": "yes",
                        "confidence": "0.91",
                    }
                ],
            )
            self._write_csv(
                source_b,
                [
                    {
                        "expression": " take   off ",
                        "original_order": "3",
                        "source": "source_b",
                        "reviewed_as": "multi-word verb",
                        "difficulty": "B2",
                        "commonality": "medium",
                        "added": "no",
                        "confidence": "0.73",
                    }
                ],
            )

            records = build_phrase_inventory_records([source_a, source_b])

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["normalized_form"], "take off")
        self.assertEqual(record["display_form"], "Take off")
        self.assertEqual(record["phrase_kind"], "phrasal_verb")
        self.assertEqual(len(record["source_provenance"]), 2)
        self.assertEqual(
            [item["source"] for item in record["source_provenance"]],
            ["source_a", "source_b"],
        )
        self.assertEqual(record["seed_metadata"]["source_count"], 2)
        self.assertEqual(record["seed_metadata"]["raw_reviewed_as"], "phrasal verb")

    def test_build_phrase_inventory_records_normalizes_qualitative_confidence_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_csv = root / "reviewed.csv"
            self._write_csv(
                source_csv,
                [
                    {
                        "expression": "Listen up",
                        "original_order": "1",
                        "source": "curated_phrasals",
                        "reviewed_as": "phrasal verb",
                        "difficulty": "medium",
                        "commonality": "common",
                        "added": "no",
                        "confidence": "high",
                    }
                ],
            )

            records = build_phrase_inventory_records([source_csv])

        self.assertEqual(records[0]["source_provenance"][0]["raw_confidence"], 0.9)
        self.assertEqual(records[0]["seed_metadata"]["review_confidence"], 0.9)
