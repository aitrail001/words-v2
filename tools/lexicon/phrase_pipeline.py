"""Phrase enrichment pipeline helpers for lexicon offline runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.ids import make_entry_id
from tools.lexicon.inventory import build_seed_inventory, normalize_surface_text
from tools.lexicon.jsonl_io import write_jsonl


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_phrase_snapshot_rows(
    *,
    phrases: Iterable[dict[str, Any]],
    snapshot_id: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    timestamp = created_at or _utc_now()
    for raw_row in phrases:
        if not isinstance(raw_row, dict):
            continue
        display_form = str(raw_row.get("phrase") or raw_row.get("display_form") or "").strip()
        normalized_form = normalize_surface_text(display_form)
        if not normalized_form or normalized_form in seen:
            continue
        phrase_kind = str(raw_row.get("phrase_kind") or "multiword_expression").strip() or "multiword_expression"
        seen.add(normalized_form)
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "entry_kind": "phrase",
                "entry_type": "phrase",
                "entry_id": make_entry_id("phrase", normalized_form),
                "normalized_form": normalized_form,
                "display_form": display_form,
                "phrase_kind": phrase_kind,
                "language": str(raw_row.get("language") or "en").strip() or "en",
                "source_provenance": list(raw_row.get("source_provenance") or [{"source": "phrase_seed"}]),
                "created_at": timestamp,
            }
        )
    return rows


def write_phrase_snapshot(output_dir: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_jsonl(output_dir / "phrases.jsonl", rows)
