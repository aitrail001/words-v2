"""Lightweight learner-reference pipeline helpers for lexicon offline runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.ids import make_entry_id
from tools.lexicon.inventory import normalize_surface_text
from tools.lexicon.jsonl_io import write_jsonl


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_localized_text_map(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    normalized: dict[str, str] = {}
    for key, item in value.items():
        locale = str(key).strip()
        text = str(item or "").strip()
        if not locale or not text:
            continue
        normalized[locale] = text
    return normalized or None


def build_reference_snapshot_rows(
    *,
    references: Iterable[dict[str, Any]],
    snapshot_id: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    timestamp = created_at or _utc_now()
    for raw_row in references:
        if not isinstance(raw_row, dict):
            continue
        display_form = str(raw_row.get("display_form") or raw_row.get("reference") or "").strip()
        normalized_form = normalize_surface_text(display_form)
        if not normalized_form or normalized_form in seen:
            continue
        reference_type = str(raw_row.get("reference_type") or "name").strip() or "name"
        translation_mode = str(raw_row.get("translation_mode") or "keep_original").strip() or "keep_original"
        brief_description = str(raw_row.get("brief_description") or "").strip()
        pronunciation = str(raw_row.get("pronunciation") or "").strip()
        seen.add(normalized_form)
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "entry_kind": "reference",
                "entry_type": "reference",
                "entry_id": make_entry_id("reference", normalized_form),
                "normalized_form": normalized_form,
                "display_form": display_form,
                "reference_type": reference_type,
                "translation_mode": translation_mode,
                "brief_description": brief_description,
                "pronunciation": pronunciation,
                "localized_display_form": _normalize_localized_text_map(raw_row.get("localized_display_form")),
                "localized_brief_description": _normalize_localized_text_map(raw_row.get("localized_brief_description")),
                "learner_tip": str(raw_row.get("learner_tip") or "").strip() or None,
                "language": str(raw_row.get("language") or "en").strip() or "en",
                "source_provenance": list(raw_row.get("source_provenance") or [{"source": "reference_seed"}]),
                "created_at": timestamp,
            }
        )
    return rows


def write_reference_snapshot(output_dir: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_jsonl(output_dir / "references.jsonl", rows)
