"""Helpers for building normalized phrase inventory rows from reviewed CSV sources."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.inventory import normalize_surface_text

_PHRASAL_VERB_LABELS = {
    "phrasal verb",
    "prepositional verb",
    "phrasal-prepositional verb",
    "multi-word verb",
}

_QUALITATIVE_CONFIDENCE = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.9,
}


def map_reviewed_phrase_kind(raw_label: Any) -> str:
    label = str(raw_label or "").strip().lower()
    if label in _PHRASAL_VERB_LABELS:
        return "phrasal_verb"
    if label == "idiom":
        return "idiom"
    return "multiword_expression"


def _normalize_optional_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    return int(text)


def _normalize_optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    qualitative = _QUALITATIVE_CONFIDENCE.get(text.lower())
    if qualitative is not None:
        return qualitative
    return float(text)


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_added_flag(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"yes", "true", "1", "y"}:
        return True
    if text in {"no", "false", "0", "n"}:
        return False
    return None


def _provenance_from_row(row: dict[str, Any], *, source_path: Path) -> dict[str, Any]:
    return {
        "source": _normalize_optional_text(row.get("source")) or source_path.stem,
        "source_file": str(source_path),
        "original_order": _normalize_optional_int(row.get("original_order")),
        "raw_reviewed_as": _normalize_optional_text(row.get("reviewed_as")),
        "raw_difficulty": _normalize_optional_text(row.get("difficulty")),
        "raw_commonality": _normalize_optional_text(row.get("commonality")),
        "raw_confidence": _normalize_optional_float(row.get("confidence")),
        "added": _normalize_added_flag(row.get("added")),
    }


def _seed_metadata_from_row(row: dict[str, Any], *, source_order: int | None, review_confidence: float | None) -> dict[str, Any]:
    return {
        "raw_reviewed_as": _normalize_optional_text(row.get("reviewed_as")),
        "commonality": _normalize_optional_text(row.get("commonality")),
        "difficulty": _normalize_optional_text(row.get("difficulty")),
        "review_confidence": review_confidence,
        "added": _normalize_added_flag(row.get("added")),
        "source_order": source_order,
        "source_count": 1,
    }


def build_phrase_inventory_records(source_paths: Iterable[Path]) -> list[dict[str, Any]]:
    merged_rows: dict[str, dict[str, Any]] = {}
    for raw_source_path in source_paths:
        source_path = Path(raw_source_path)
        with source_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                display_form = str(row.get("expression") or "").strip()
                normalized_form = normalize_surface_text(display_form)
                if not normalized_form:
                    continue
                phrase_kind = map_reviewed_phrase_kind(row.get("reviewed_as"))
                provenance = _provenance_from_row(row, source_path=source_path)
                record = merged_rows.get(normalized_form)
                if record is None:
                    seed_metadata = _seed_metadata_from_row(
                        row,
                        source_order=provenance["original_order"],
                        review_confidence=provenance["raw_confidence"],
                    )
                    merged_rows[normalized_form] = {
                        "phrase": display_form,
                        "display_form": display_form,
                        "normalized_form": normalized_form,
                        "phrase_kind": phrase_kind,
                        "language": "en",
                        "source_provenance": [provenance],
                        "seed_metadata": seed_metadata,
                    }
                    continue

                record["source_provenance"].append(provenance)
                record["seed_metadata"]["source_count"] = len(record["source_provenance"])
                if not record.get("display_form"):
                    record["display_form"] = display_form
                    record["phrase"] = display_form

    return list(merged_rows.values())
