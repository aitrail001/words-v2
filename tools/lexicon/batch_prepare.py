"""Batch request preparation helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.batch_ledger import append_jsonl_rows, build_batch_custom_id, build_batch_job_rows, load_jsonl_rows, parse_batch_custom_id, write_jsonl_rows
from tools.lexicon.jsonl_io import write_jsonl


def build_batch_request_rows(
    *,
    snapshot_id: str,
    model: str,
    prompt_version: str,
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    request_rows: list[dict[str, Any]] = []
    for row in rows:
        entry_kind = str(row.get("entry_kind") or "word").strip().lower()
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            continue
        custom_id = build_batch_custom_id(
            entry_kind=entry_kind,
            snapshot_id=snapshot_id,
            entry_id=entry_id,
            attempt=1,
        )
        request_rows.append(
            {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/responses",
                "body": {
                    "entry_kind": entry_kind,
                    "entry_id": entry_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "prompt_version": prompt_version,
                    "source_row": dict(row),
                },
            }
        )
    return request_rows


def write_batch_request_rows(output_path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_jsonl(output_path, rows)


def build_retry_batch_request_rows(
    *,
    snapshot_id: str,
    model: str,
    prompt_version: str,
    request_rows: Iterable[dict[str, Any]],
    failed_custom_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    failed_custom_ids = failed_custom_ids or set()
    retry_rows: list[dict[str, Any]] = []
    for row in request_rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        if failed_custom_ids and custom_id not in failed_custom_ids:
            continue
        parsed = parse_batch_custom_id(custom_id)
        attempt = int(parsed["attempt"]) + 1
        retry_custom_id = build_batch_custom_id(
            entry_kind=str(parsed["entry_kind"]),
            snapshot_id=snapshot_id,
            entry_id=str(parsed["entry_id"]),
            attempt=attempt,
        )
        body = dict(row.get("body") or {})
        body["model"] = model
        body["prompt_version"] = prompt_version
        body["attempt"] = attempt
        retry_rows.append(
            {
                "custom_id": retry_custom_id,
                "method": "POST",
                "url": "/responses",
                "body": body,
            }
        )
    return retry_rows
