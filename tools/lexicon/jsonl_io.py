from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import json

from tools.lexicon.text_safety import validate_nested_no_control_characters


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for index, row in enumerate(rows):
            validate_nested_no_control_characters(row, field=f"rows[{index}]")
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    return path


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        for index, row in enumerate(rows):
            validate_nested_no_control_characters(row, field=f"rows[{index}]")
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows
