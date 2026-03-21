from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.validate import validate_compiled_record


DECISION_SCHEMA_VERSION = "lexicon_review_decision.v1"
ALLOWED_DECISIONS = {"approved", "rejected", "reopened"}


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_payload(payload: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))


def _artifact_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_decisions(decisions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in decisions:
        row = dict(raw)
        row["entry_id"] = str(row.get("entry_id") or "").strip()
        row["entry_type"] = str(row.get("entry_type") or "").strip().lower()
        row["decision"] = str(row.get("decision") or "").strip().lower()
        if not row["entry_id"]:
            raise ValueError("Review decision entry_id is required")
        if row["entry_type"] not in {"word", "phrase", "reference"}:
            raise ValueError(f"Review decision entry_type is invalid for {row['entry_id']}")
        if row["decision"] not in ALLOWED_DECISIONS:
            raise ValueError(f"Review decision value is invalid for {row['entry_id']}: {row['decision']}")
        normalized.append(row)
    return normalized


def materialize_review_outputs(
    *,
    compiled_path: Path,
    decisions_input_path: Path | None = None,
    decisions: Iterable[dict[str, Any]] | None = None,
    decisions_output_path: Path | None = None,
    approved_output_path: Path | None = None,
    rejected_output_path: Path | None = None,
    regenerate_output_path: Path | None = None,
) -> dict[str, Any]:
    compiled_rows = read_jsonl(compiled_path)
    if not compiled_rows:
        raise ValueError(f"No compiled rows found at {compiled_path}")

    for index, row in enumerate(compiled_rows, start=1):
        errors = validate_compiled_record(row)
        if errors:
            raise ValueError(f"Compiled row {index} failed validation: {'; '.join(errors)}")

    artifact_sha256 = _artifact_sha256(compiled_path)
    compiled_by_id: dict[str, dict[str, Any]] = {}
    payload_sha_by_id: dict[str, str] = {}
    for row in compiled_rows:
        entry_id = str(row.get("entry_id") or "").strip()
        if entry_id in compiled_by_id:
            raise ValueError(f"Duplicate compiled entry_id in artifact: {entry_id}")
        compiled_by_id[entry_id] = row
        payload_sha_by_id[entry_id] = _sha256_payload(row)

    raw_decisions = decisions
    if raw_decisions is None:
        if decisions_input_path is None:
            raise ValueError("review-materialize requires decisions or decisions_input_path")
        raw_decisions = read_jsonl(decisions_input_path)
    decision_rows = _normalize_decisions(raw_decisions)
    seen_entry_ids: set[str] = set()
    seen_artifact_hashes: set[str] = set()
    for row in decision_rows:
        entry_id = row["entry_id"]
        if entry_id in seen_entry_ids:
            raise ValueError(f"Duplicate review decision for entry_id {entry_id}")
        seen_entry_ids.add(entry_id)
        if entry_id not in compiled_by_id:
            raise ValueError(f"Unknown review decision entry_id {entry_id}")
        supplied_artifact_sha = str(row.get("artifact_sha256") or "").strip()
        if supplied_artifact_sha:
            seen_artifact_hashes.add(supplied_artifact_sha)
        supplied_payload_sha = str(row.get("compiled_payload_sha256") or "").strip()
        if supplied_payload_sha and supplied_payload_sha != payload_sha_by_id[entry_id]:
            raise ValueError(f"Review decision compiled_payload_sha256 mismatch for {entry_id}")

    if len(seen_artifact_hashes) > 1:
        raise ValueError("Review decisions contain mixed artifact_sha256 values")
    if seen_artifact_hashes and artifact_sha256 not in seen_artifact_hashes:
        first_entry_id = decision_rows[0]["entry_id"]
        raise ValueError(f"Review decision artifact_sha256 mismatch for {first_entry_id}")

    missing_entry_ids = sorted(set(compiled_by_id) - seen_entry_ids)
    if missing_entry_ids:
        preview = ", ".join(missing_entry_ids[:10])
        raise ValueError(f"Missing review decisions for entry_ids: {preview}")

    approved_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    regenerate_rows: list[dict[str, Any]] = []
    finalized_decisions: list[dict[str, Any]] = []

    for row in decision_rows:
        entry_id = row["entry_id"]
        compiled_row = compiled_by_id[entry_id]
        payload_sha = payload_sha_by_id[entry_id]
        finalized = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "artifact_sha256": artifact_sha256,
            "entry_id": entry_id,
            "entry_type": row["entry_type"],
            "decision": row["decision"],
            "decision_reason": row.get("decision_reason"),
            "compiled_payload_sha256": payload_sha,
            "reviewed_by": row.get("reviewed_by"),
            "reviewed_at": row.get("reviewed_at"),
        }
        finalized_decisions.append(finalized)
        if row["decision"] == "approved":
            approved_rows.append(compiled_row)
            continue
        rejected_rows.append({**compiled_row, **finalized})
        if row["decision"] == "rejected":
            regenerate_rows.append(
                {
                    "schema_version": DECISION_SCHEMA_VERSION,
                    "artifact_sha256": artifact_sha256,
                    "entry_id": entry_id,
                    "entry_type": row["entry_type"],
                    "normalized_form": compiled_row.get("normalized_form"),
                    "decision_reason": row.get("decision_reason"),
                    "compiled_payload_sha256": payload_sha,
                }
            )

    if decisions_output_path is not None:
        write_jsonl(decisions_output_path, finalized_decisions)
    if approved_output_path is not None:
        write_jsonl(approved_output_path, approved_rows)
    if rejected_output_path is not None:
        write_jsonl(rejected_output_path, rejected_rows)
    if regenerate_output_path is not None:
        write_jsonl(regenerate_output_path, regenerate_rows)

    return {
        "artifact_sha256": artifact_sha256,
        "decision_count": len(finalized_decisions),
        "approved_count": len(approved_rows),
        "rejected_count": len(rejected_rows),
        "regenerate_count": len(regenerate_rows),
    }
