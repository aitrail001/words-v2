#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _resolve_failures_path(path_arg: str) -> Path:
    path = Path(path_arg)
    if path.is_dir():
        return path / "enrich.failures.jsonl"
    return path


def _iter_failure_rows(failures_path: Path) -> Iterable[dict]:
    with failures_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show realtime enrichment failure rows and their error messages."
    )
    parser.add_argument(
        "path",
        help="snapshot directory or enrich.failures.jsonl path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit compact JSON rows instead of tab-separated text",
    )
    args = parser.parse_args()

    failures_path = _resolve_failures_path(args.path)
    if not failures_path.exists():
        raise SystemExit(f"failures file not found: {failures_path}")

    for row in _iter_failure_rows(failures_path):
        payload = {
            "lexeme_id": row.get("lexeme_id"),
            "lemma": row.get("lemma"),
            "error": row.get("error"),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"{payload['lemma']}\t{payload['error']}\t{payload['lexeme_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
