from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.lexicon.runtime_logging import RuntimeLogConfig, RuntimeLogger


class RuntimeLoggingTests(unittest.TestCase):
    def _clock(self) -> datetime:
        return datetime(2026, 3, 23, 3, 24, 13, tzinfo=timezone.utc)

    def test_info_level_emits_terminal_line_and_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            stream = io.StringIO()
            logger = RuntimeLogger(
                RuntimeLogConfig(level="info", log_file=log_file),
                stream=stream,
                clock=self._clock,
            )

            logger.info("command-start", "Starting enrich", command="enrich", snapshot_dir="/tmp/snapshot")

            self.assertEqual(
                stream.getvalue().strip(),
                "2026-03-23T03:24:13Z [info] command-start: Starting enrich command=enrich snapshot_dir=/tmp/snapshot",
            )
            rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows, [
                {
                    "timestamp": "2026-03-23T03:24:13Z",
                    "level": "info",
                    "event": "command-start",
                    "message": "Starting enrich",
                    "fields": {
                        "command": "enrich",
                        "snapshot_dir": "/tmp/snapshot",
                    },
                }
            ])

    def test_quiet_level_suppresses_terminal_and_file_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            stream = io.StringIO()
            logger = RuntimeLogger(
                RuntimeLogConfig(level="quiet", log_file=log_file),
                stream=stream,
                clock=self._clock,
            )

            logger.info("item-progress", "Processing entry", entry_id="lx_run")

            self.assertEqual(stream.getvalue(), "")
            self.assertFalse(log_file.exists())

    def test_info_level_suppresses_debug_events_in_terminal_and_file_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            stream = io.StringIO()
            logger = RuntimeLogger(
                RuntimeLogConfig(level="info", log_file=log_file),
                stream=stream,
                clock=self._clock,
            )

            logger.debug("retry-scheduled", "Retrying lexeme", lexeme_id="lx_run")

            self.assertEqual(stream.getvalue(), "")
            self.assertFalse(log_file.exists())

    def test_debug_level_prints_debug_events_and_redacts_payload_like_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            stream = io.StringIO()
            logger = RuntimeLogger(
                RuntimeLogConfig(level="debug", log_file=log_file),
                stream=stream,
                clock=self._clock,
            )

            logger.debug(
                "retry-scheduled",
                "Retrying lexeme",
                lexeme_id="lx_run",
                payload={"secret": "value", "nested": ["do not leak"]},
                attempt=2,
            )

            self.assertEqual(
                stream.getvalue().strip(),
                "2026-03-23T03:24:13Z [debug] retry-scheduled: Retrying lexeme attempt=2 lexeme_id=lx_run payload=[redacted]",
            )
            rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(rows[0]["level"], "debug")
            self.assertEqual(rows[0]["fields"]["payload"], "[redacted]")
            self.assertNotIn("secret", log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
