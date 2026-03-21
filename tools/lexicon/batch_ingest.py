"""Batch output ingestion helpers for lexicon offline runs."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.batch_ledger import append_jsonl_rows, load_jsonl_rows


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_batch_result_rows(
    *,
    request_rows: Iterable[dict[str, Any]],
    output_rows: Iterable[dict[str, Any]],
    ingested_at: str,
) -> list[dict[str, Any]]:
    requests_by_custom_id = {
        str(row.get("custom_id") or "").strip(): dict(row)
        for row in request_rows
        if str(row.get("custom_id") or "").strip()
    }
    results: list[dict[str, Any]] = []
    for output_row in output_rows:
        custom_id = str(output_row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        request_row = requests_by_custom_id.get(custom_id, {})
        response_payload = output_row.get("response")
        if response_payload is None:
            response_payload = output_row.get("body")
        error_payload = output_row.get("error") or output_row.get("response_error")
        has_error = error_payload is not None
        status = "failed" if has_error else "accepted"
        validation_status = "invalid" if has_error else "valid"
        qc_status = "pending" if not has_error else "needs_review"
        attempt = int(output_row.get("attempt") or request_row.get("attempt") or 1)
        result_row = {
            "custom_id": custom_id,
            "entry_id": output_row.get("entry_id") or request_row.get("entry_id"),
            "entry_kind": output_row.get("entry_kind") or request_row.get("entry_kind"),
            "status": status,
            "validation_status": validation_status,
            "qc_status": qc_status,
            "attempt": attempt,
            "model": output_row.get("model") or request_row.get("body", {}).get("model"),
            "output_hash": _stable_hash(response_payload) if response_payload is not None else None,
            "error_class": error_payload.get("class") if isinstance(error_payload, dict) else None,
            "error_detail": error_payload.get("message") if isinstance(error_payload, dict) else error_payload,
            "ingested_at": ingested_at,
            "raw_output": dict(output_row),
        }
        results.append(result_row)
    return results


def split_batch_result_rows(result_rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for row in result_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "accepted":
            accepted_rows.append(dict(row))
        else:
            failure_rows.append(dict(row))
    return accepted_rows, failure_rows


def ingest_batch_outputs(
    snapshot_dir: Path,
    output_path: Path,
    *,
    request_path: Path | None = None,
    batch_output_path: Path,
    ingested_at: str,
    failure_output_path: Path | None = None,
) -> list[dict[str, Any]]:
    request_rows = load_jsonl_rows(request_path or (snapshot_dir / "batch_requests.jsonl"))
    output_rows = load_jsonl_rows(batch_output_path)
    result_rows = build_batch_result_rows(
        request_rows=request_rows,
        output_rows=output_rows,
        ingested_at=ingested_at,
    )
    _, failure_rows = split_batch_result_rows(result_rows)
    if result_rows:
        append_jsonl_rows(output_path, result_rows)
    if failure_output_path is not None and failure_rows:
        append_jsonl_rows(failure_output_path, failure_rows)
    return result_rows


def build_batch_output_summary(result_rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "accepted": 0, "failed": 0, "valid": 0, "invalid": 0, "pending": 0, "needs_review": 0}
    for row in result_rows:
        summary["total"] += 1
        for field in ("status", "validation_status", "qc_status"):
            value = str(row.get(field) or "").strip().lower()
            if value in summary:
                summary[value] += 1
    return summary
