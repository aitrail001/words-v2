"""Batch ledger helpers for lexicon offline runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.jsonl_io import append_jsonl, read_jsonl, write_jsonl


@dataclass(frozen=True)
class BatchArtifactPaths:
    snapshot_dir: Path
    batch_requests_path: Path
    batch_jobs_path: Path
    batch_inputs_dir: Path

    @classmethod
    def from_snapshot_dir(cls, snapshot_dir: Path) -> "BatchArtifactPaths":
        return cls(
            snapshot_dir=snapshot_dir,
            batch_requests_path=snapshot_dir / "batch_requests.jsonl",
            batch_jobs_path=snapshot_dir / "batch_jobs.jsonl",
            batch_inputs_dir=snapshot_dir / "batches",
        )


def build_batch_custom_id(*, entry_kind: str, snapshot_id: str, entry_id: str, attempt: int = 1) -> str:
    normalized_kind = str(entry_kind).strip().lower()
    normalized_snapshot = str(snapshot_id).strip()
    normalized_entry = str(entry_id).strip()
    return f"{normalized_kind}:{normalized_snapshot}:{normalized_entry}:attempt{int(attempt)}"


def parse_batch_custom_id(custom_id: str) -> dict[str, object]:
    parts = str(custom_id).split(":")
    if len(parts) != 4 or not parts[3].startswith("attempt"):
        raise ValueError(f"Invalid batch custom_id: {custom_id}")
    attempt = int(parts[3].replace("attempt", "", 1))
    return {
        "entry_kind": parts[0],
        "snapshot_id": parts[1],
        "entry_id": parts[2],
        "attempt": attempt,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [dict(row) for row in read_jsonl(path)]


def write_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_jsonl(path, rows)


def append_jsonl_rows(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return append_jsonl(path, rows)


def build_batch_job_rows(
    *,
    batch_id: str | None,
    input_file_id: str | None,
    request_rows: Iterable[dict[str, Any]],
    status: str = "submitted",
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    timestamp = created_at or utc_now()
    job_rows: list[dict[str, Any]] = []
    for row in request_rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        parsed = parse_batch_custom_id(custom_id)
        job_rows.append(
            {
                "custom_id": custom_id,
                "entry_kind": parsed["entry_kind"],
                "snapshot_id": parsed["snapshot_id"],
                "entry_id": parsed["entry_id"],
                "attempt": parsed["attempt"],
                "status": status,
                "batch_id": batch_id,
                "input_file_id": input_file_id,
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    return job_rows


def latest_rows_by_custom_id(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        parsed = parse_batch_custom_id(custom_id)
        current = latest.get(custom_id)
        if current is None:
            latest[custom_id] = dict(row)
            continue
        current_parsed = parse_batch_custom_id(str(current.get("custom_id") or custom_id))
        if int(parsed["attempt"]) >= int(current_parsed["attempt"]):
            latest[custom_id] = dict(row)
    return latest


def latest_rows_by_entry_lineage(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        parsed = parse_batch_custom_id(custom_id)
        lineage_key = (
            str(parsed["entry_kind"]),
            str(parsed["snapshot_id"]),
            str(parsed["entry_id"]),
        )
        current = latest.get(lineage_key)
        if current is None:
            latest[lineage_key] = dict(row)
            continue
        current_parsed = parse_batch_custom_id(str(current.get("custom_id") or custom_id))
        if int(parsed["attempt"]) >= int(current_parsed["attempt"]):
            latest[lineage_key] = dict(row)
    return latest


def summarize_batch_jobs(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": 0,
        "submitted": 0,
        "completed": 0,
        "failed": 0,
        "pending": 0,
    }
    for row in rows:
        summary["total"] += 1
        status = str(row.get("status") or "pending").strip().lower()
        if status not in summary:
            summary[status] = 0
        summary[status] += 1
    return summary
