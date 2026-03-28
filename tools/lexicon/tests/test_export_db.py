import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lexicon.export_db import export_db_fixture, load_export_rows


class ExportDbTests(unittest.TestCase):
    def test_export_db_fixture_streams_rows_without_materializing_load_export_rows(self) -> None:
        def _rows():
            yield {"entry_type": "word", "word": "run"}
            yield {"entry_type": "phrase", "word": "take off"}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "approved.jsonl"
            with patch("tools.lexicon.export_db.load_export_rows", side_effect=AssertionError("should not materialize full export first")), \
                 patch("tools.lexicon.export_db.iter_export_rows", return_value=_rows()):
                summary = export_db_fixture(output_path)

            self.assertEqual(summary["row_count"], 2)
            self.assertEqual(summary["word_count"], 1)
            self.assertEqual(summary["phrase_count"], 1)
            self.assertEqual(output_path.read_text(encoding="utf-8").splitlines(), [
                json.dumps({"entry_type": "word", "word": "run"}),
                json.dumps({"entry_type": "phrase", "word": "take off"}),
            ])

    def test_load_export_rows_materializes_streamed_iterator(self) -> None:
        with patch(
            "tools.lexicon.export_db.iter_export_rows",
            return_value=iter([{"entry_type": "word", "word": "run"}]),
        ):
            rows = load_export_rows()

        self.assertEqual(rows, [{"entry_type": "word", "word": "run"}])


if __name__ == "__main__":
    unittest.main()
