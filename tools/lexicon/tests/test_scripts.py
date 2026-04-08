import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_SHOW_FAILURES_SCRIPT = _REPO_ROOT / "tools/lexicon/scripts/show-failures.py"
_SHOW_DISCARDED_SCRIPT = _REPO_ROOT / "tools/lexicon/scripts/show-discarded.py"
_MONITOR_ENRICH_SCRIPT = _REPO_ROOT / "tools/lexicon/scripts/monitor-enrich.zsh"


class ScriptTests(unittest.TestCase):
    def _resolve_zsh(self) -> str:
        for candidate in ("/bin/zsh", "/usr/bin/zsh", shutil.which("zsh")):
            if candidate and Path(candidate).exists():
                return str(candidate)
        self.skipTest("zsh is not available in this environment")

    def _run_python_script(self, script_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script_path), *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def _run_monitor_script(self, snapshot_dir: Path) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ)
        env["INTERVAL_SECONDS"] = "0"
        env["TAIL_ROWS"] = "0"
        return subprocess.run(
            [self._resolve_zsh(), str(_MONITOR_ENRICH_SCRIPT), "--once", "--no-tail", str(snapshot_dir)],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_show_failures_reads_staged_ledgers_from_snapshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "enrich.core.failures.jsonl").write_text(
                json.dumps({"lexeme_id": "lx_run", "lemma": "run", "error": "core timeout"}) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "enrich.translations.failures.jsonl").write_text(
                json.dumps({"entry_id": "lx_run", "sense_id": "sn_lx_run_1", "error": "translation timeout"}) + "\n",
                encoding="utf-8",
            )

            result = self._run_python_script(_SHOW_FAILURES_SCRIPT, str(snapshot_dir), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(
                rows,
                [
                    {
                        "stage": "core",
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "entry_id": None,
                        "sense_id": None,
                        "error": "core timeout",
                    },
                    {
                        "stage": "translations",
                        "lexeme_id": None,
                        "lemma": None,
                        "entry_id": "lx_run",
                        "sense_id": "sn_lx_run_1",
                        "error": "translation timeout",
                    },
                ],
            )

    def test_show_discarded_reads_staged_core_decisions_from_snapshot_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "enrich.core.decisions.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"lexeme_id": "lx_run", "lemma": "run", "decision": "discard", "discard_reason": "not learner-worthy"}),
                        json.dumps({"lexeme_id": "lx_play", "lemma": "play", "decision": "keep_standard", "discard_reason": None}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = self._run_python_script(_SHOW_DISCARDED_SCRIPT, str(snapshot_dir), "--json")

            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            self.assertEqual(
                rows,
                [
                    {
                        "stage": "core",
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "discard_reason": "not learner-worthy",
                    }
                ],
            )

    def test_monitor_enrich_once_reports_staged_artifact_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "words.enriched.core.jsonl").write_text("{}\n{}\n", encoding="utf-8")
            (snapshot_dir / "words.translations.jsonl").write_text("{}\n", encoding="utf-8")
            (snapshot_dir / "enrich.core.checkpoint.jsonl").write_text("{}\n{}\n{}\n", encoding="utf-8")
            (snapshot_dir / "enrich.translations.checkpoint.jsonl").write_text("{}\n{}\n", encoding="utf-8")

            result = self._run_monitor_script(snapshot_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("words.enriched.core.jsonl", result.stdout)
            self.assertIn("words.translations.jsonl", result.stdout)
            self.assertIn("enrich.core.checkpoint.jsonl", result.stdout)
            self.assertIn("enrich.translations.checkpoint.jsonl", result.stdout)
            self.assertRegex(result.stdout, r"words\.enriched\.core\.jsonl\s+2")
            self.assertRegex(result.stdout, r"enrich\.translations\.checkpoint\.jsonl\s+2")
