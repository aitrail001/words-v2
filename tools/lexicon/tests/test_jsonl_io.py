from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.lexicon.jsonl_io import append_jsonl, write_jsonl


class JsonlIoTests(unittest.TestCase):
    def test_write_jsonl_rejects_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.jsonl"

            with self.assertRaisesRegex(ValueError, "control character"):
                write_jsonl(path, [{"word": "cripple", "bad": "da\x00nar"}])

    def test_append_jsonl_rejects_control_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.jsonl"
            write_jsonl(path, [{"word": "bank"}])

            with self.assertRaisesRegex(ValueError, "control character"):
                append_jsonl(path, [{"word": "render", "bad": "\x00هذا الشكل"}])
