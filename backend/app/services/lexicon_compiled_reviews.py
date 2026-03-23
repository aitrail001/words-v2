from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.services.lexicon_jsonl_reviews import (
    APPROVED_FILENAME,
    DECISIONS_FILENAME,
    REGENERATE_FILENAME,
    REJECTED_FILENAME,
)


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def default_compiled_review_output_dir(batch: LexiconArtifactReviewBatch, settings: Settings) -> Path:
    source_reference = str(batch.source_reference or "").strip()
    if source_reference:
        snapshot_root = Path(settings.lexicon_snapshot_root).expanduser()
        if not snapshot_root.is_absolute():
            snapshot_root = (Path.cwd() / snapshot_root).resolve()
        candidate = (snapshot_root / source_reference / "reviewed").resolve()
        try:
            candidate.relative_to(snapshot_root)
            return candidate
        except ValueError:
            pass
    return (Path.cwd() / "data" / "lexicon" / "compiled-review" / str(batch.id)).resolve()


def _decision_status(item: LexiconArtifactReviewItem) -> str:
    if item.review_status == "approved":
        return "approved"
    if item.review_status == "rejected":
        return "rejected"
    return "reopened"


def materialized_rows(
    batch: LexiconArtifactReviewBatch,
    items: Sequence[LexiconArtifactReviewItem],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    approved_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    regenerate_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    for item in items:
        if item.review_status not in {"approved", "rejected"}:
            continue
        decision = {
            "schema_version": "lexicon_review_decision.v1",
            "artifact_sha256": batch.artifact_sha256,
            "entry_id": item.entry_id,
            "entry_type": item.entry_type,
            "decision": _decision_status(item),
            "decision_reason": item.decision_reason,
            "compiled_payload_sha256": item.compiled_payload_sha256,
            "reviewed_by": str(item.reviewed_by) if item.reviewed_by else None,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        }
        decision_rows.append(decision)
        if item.review_status == "approved" and item.import_eligible:
            approved_rows.append(json_safe(item.compiled_payload))
            continue
        if item.review_status == "rejected":
            rejected_rows.append(
                json_safe(
                    {
                        **item.compiled_payload,
                        "entry_id": item.entry_id,
                        "entry_type": item.entry_type,
                        "artifact_sha256": batch.artifact_sha256,
                        "decision": _decision_status(item),
                        "decision_reason": item.decision_reason,
                        "compiled_payload_sha256": item.compiled_payload_sha256,
                        "reviewed_by": str(item.reviewed_by) if item.reviewed_by else None,
                        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
                    }
                )
            )
            if item.regen_requested:
                regenerate_rows.append(
                    json_safe(
                        {
                            "schema_version": "lexicon_review_decision.v1",
                            "entry_id": item.entry_id,
                            "entry_type": item.entry_type,
                            "normalized_form": item.normalized_form,
                            "artifact_sha256": batch.artifact_sha256,
                            "compiled_payload_sha256": item.compiled_payload_sha256,
                            "decision_reason": item.decision_reason,
                        }
                    )
                )
    return approved_rows, rejected_rows, regenerate_rows, decision_rows


def write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Output path is not writable: {path}",
        ) from exc


def materialize_compiled_review_batch(
    db: Session,
    *,
    batch_id: uuid.UUID,
    output_dir: Path,
    settings: Settings,
) -> dict[str, Any]:
    batch_result = db.execute(select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.id == batch_id))
    batch = batch_result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Compiled review batch not found")

    items_result = db.execute(
        select(LexiconArtifactReviewItem)
        .where(LexiconArtifactReviewItem.batch_id == batch_id)
        .order_by(LexiconArtifactReviewItem.review_priority.asc(), LexiconArtifactReviewItem.display_text.asc())
    )
    items = list(items_result.scalars().all())

    approved_rows, rejected_rows, regenerate_rows, decision_rows = materialized_rows(batch, items)
    effective_output_dir = output_dir or default_compiled_review_output_dir(batch, settings)
    approved_output_path = effective_output_dir / APPROVED_FILENAME
    rejected_output_path = effective_output_dir / REJECTED_FILENAME
    regenerate_output_path = effective_output_dir / REGENERATE_FILENAME
    decisions_output_path = effective_output_dir / DECISIONS_FILENAME
    write_jsonl(approved_output_path, approved_rows)
    write_jsonl(rejected_output_path, rejected_rows)
    write_jsonl(regenerate_output_path, regenerate_rows)
    write_jsonl(decisions_output_path, decision_rows)
    return {
        "decision_count": len(decision_rows),
        "approved_count": len(approved_rows),
        "rejected_count": len(rejected_rows),
        "regenerate_count": len(regenerate_rows),
        "decisions_output_path": str(decisions_output_path),
        "approved_output_path": str(approved_output_path),
        "rejected_output_path": str(rejected_output_path),
        "regenerate_output_path": str(regenerate_output_path),
    }
