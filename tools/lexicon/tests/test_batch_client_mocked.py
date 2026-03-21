from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.lexicon.batch_client import BatchClient


class BatchClientMockedTests(unittest.TestCase):
    def test_batch_client_methods_delegate_to_transport(self) -> None:
        calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

        def transport(operation: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
            calls.append((operation, payload, headers))
            return {"operation": operation, "payload": payload}

        client = BatchClient(transport=transport)

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "batch.jsonl"
            file_path.write_text("{}", encoding="utf-8")

            upload = client.upload_batch_file(file_path, purpose="batch")
            create = client.create_batch(input_file_id="file-1", endpoint="/responses")
            status = client.get_batch(batch_id="batch-1")
            download = client.download_file(file_id="file-2")

        self.assertEqual(upload["operation"], "upload_batch_file")
        self.assertEqual(create["operation"], "create_batch")
        self.assertEqual(status["operation"], "get_batch")
        self.assertEqual(download["operation"], "download_file")
        self.assertEqual([call[0] for call in calls], ["upload_batch_file", "create_batch", "get_batch", "download_file"])

