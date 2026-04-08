#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _resolve_failure_paths(path_arg: str) -> list[tuple[str, Path]]:
    path = Path(path_arg)
    if path.is_dir():
        candidates = [
            ("realtime", path / "enrich.failures.jsonl"),
            ("core", path / "enrich.core.failures.jsonl"),
            ("translations", path / "enrich.translations.failures.jsonl"),
        ]
        return [(stage, candidate) for stage, candidate in candidates if candidate.exists()]
    return [("file", path)]


def _iter_failure_rows(failures_path: Path) -> Iterable[dict]:
    with failures_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show enrichment failure rows and their error messages."
    )
    parser.add_argument(
        "path",
        help="snapshot directory or explicit failures JSONL path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit compact JSON rows instead of tab-separated text",
    )
    args = parser.parse_args()

    failure_paths = _resolve_failure_paths(args.path)
    if not failure_paths:
        raise SystemExit(f"failures file not found under: {args.path}")

    for stage, failures_path in failure_paths:
        if not failures_path.exists():
            raise SystemExit(f"failures file not found: {failures_path}")
        for row in _iter_failure_rows(failures_path):
            payload = {
                "stage": stage,
                "lexeme_id": row.get("lexeme_id"),
                "lemma": row.get("lemma"),
                "entry_id": row.get("entry_id"),
                "sense_id": row.get("sense_id"),
                "error": row.get("error"),
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                label = payload["lemma"] or payload["entry_id"] or "<unknown>"
                identifier = payload["lexeme_id"] or payload["sense_id"] or payload["entry_id"]
                print(f"{payload['stage']}\t{label}\t{payload['error']}\t{identifier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
