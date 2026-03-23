#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def _resolve_decisions_path(path_arg: str) -> Path:
    path = Path(path_arg)
    if path.is_dir():
        return path / "enrich.decisions.jsonl"
    return path


def _iter_discard_rows(decisions_path: Path) -> Iterable[dict]:
    with decisions_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("decision") == "discard":
                yield row


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show discarded realtime enrichment decisions and their discard reasons."
    )
    parser.add_argument(
        "path",
        help="snapshot directory or enrich.decisions.jsonl path",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit compact JSON rows instead of tab-separated text",
    )
    args = parser.parse_args()

    decisions_path = _resolve_decisions_path(args.path)
    if not decisions_path.exists():
        raise SystemExit(f"decisions file not found: {decisions_path}")

    for row in _iter_discard_rows(decisions_path):
        payload = {
            "lexeme_id": row.get("lexeme_id"),
            "lemma": row.get("lemma"),
            "discard_reason": row.get("discard_reason"),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(
                f"{payload['lemma']}\t{payload['discard_reason']}\t{payload['lexeme_id']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
