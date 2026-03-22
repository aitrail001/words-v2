"""Manual override helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.batch_ledger import load_jsonl_rows


def load_manual_overrides(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    overrides: dict[str, dict[str, Any]] = {}
    for row in load_jsonl_rows(path):
        custom_id = str(row.get("custom_id") or row.get("entry_id") or "").strip()
        if not custom_id:
            continue
        overrides[custom_id] = dict(row)
    return overrides


def apply_manual_overrides(
    rows: Iterable[dict[str, Any]],
    overrides: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        custom_id = str(row.get("custom_id") or row.get("entry_id") or "").strip()
        override = overrides.get(custom_id)
        if override is None:
            updated_rows.append(dict(row))
            continue
        merged = dict(row)
        for key in ("verdict", "confidence", "reasons", "review_notes", "model_name", "prompt_version"):
            if key in override and override[key] is not None:
                merged[key] = override[key]
        if "review_priority" in override and override["review_priority"] is not None:
            merged["review_priority"] = override["review_priority"]
        else:
            verdict = str(merged.get("verdict") or "").strip().lower()
            if verdict == "pass":
                merged["review_priority"] = 100
            elif verdict:
                merged["review_priority"] = 200
        merged["override_applied"] = True
        updated_rows.append(merged)
    return updated_rows
