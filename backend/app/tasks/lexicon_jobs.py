from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_job import LexiconJob
from app.services.lexicon_compiled_reviews import materialize_compiled_review_batch
from app.services.lexicon_compiled_review_decisions import (
    BULK_REVIEW_CHUNK_SIZE,
    add_review_item_event,
    apply_review_decision,
    recalculate_batch_counts,
    upsert_regeneration_request_sync,
    utc_now,
)
from app.services.lexicon_jobs import (
    apply_lexicon_job_completed,
    apply_lexicon_job_failed,
    apply_lexicon_job_progress,
    apply_lexicon_job_started,
)
from app.services.lexicon_jsonl_reviews import materialize_jsonl_review_outputs
from app.services.lexicon_tool_imports import import_lexicon_tool_module

settings = get_settings()
sync_engine = create_engine(settings.database_url_sync)


def _import_db_module() -> Any:
    return import_lexicon_tool_module("tools.lexicon.import_db")


def _load_job(db: Session, job_id: str) -> LexiconJob:
    result = db.execute(select(LexiconJob).where(LexiconJob.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise RuntimeError("Lexicon job not found")
    return job


def process_compiled_review_bulk_job(
    db: Session,
    *,
    job: LexiconJob,
    batch_id: uuid.UUID,
    review_status: str,
    decision_reason: str | None,
    scope: str,
    chunk_size: int,
) -> dict[str, Any]:
    batch = db.execute(
        select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.id == batch_id)
    ).scalar_one_or_none()
    if batch is None:
        raise RuntimeError("Compiled review batch not found")
    if scope != "all_pending":
        raise RuntimeError("Unsupported compiled review bulk scope")

    target_status = "pending" if review_status in {"approved", "rejected"} else None
    items = list(
        db.execute(
            select(LexiconArtifactReviewItem)
            .where(
                LexiconArtifactReviewItem.batch_id == batch_id,
                (
                    LexiconArtifactReviewItem.review_status == target_status
                    if target_status is not None
                    else LexiconArtifactReviewItem.review_status != "pending"
                ),
            )
            .order_by(
                LexiconArtifactReviewItem.review_priority.asc(),
                LexiconArtifactReviewItem.display_text.asc(),
                LexiconArtifactReviewItem.id.asc(),
            )
        ).scalars().all()
    )
    total = len(items)
    reviewed_at = utc_now()
    processed_count = 0
    initial_total_items = batch.total_items
    approved_count = batch.approved_count
    rejected_count = batch.rejected_count

    if total == 0:
        apply_lexicon_job_progress(job, progress_completed=0, progress_total=0, current_label=None)
        recalculate_batch_counts(
            batch,
            total_items=initial_total_items,
            approved_count=approved_count,
            rejected_count=rejected_count,
            updated_at=reviewed_at,
        )
        return {
            "batch_id": str(batch_id),
            "processed_count": 0,
            "approved_count": batch.approved_count,
            "rejected_count": batch.rejected_count,
            "pending_count": batch.pending_count,
            "failed_count": 0,
            "scope": scope,
            "review_status": review_status,
        }

    for start in range(0, total, chunk_size):
        chunk = items[start:start + chunk_size]
        for item in chunk:
            previous_status = apply_review_decision(
                item,
                review_status=review_status,
                decision_reason=decision_reason,
                actor_user_id=job.created_by,
                reviewed_at=reviewed_at,
            )
            if previous_status == "approved":
                approved_count -= 1
            elif previous_status == "rejected":
                rejected_count -= 1

            if review_status == "approved":
                approved_count += 1
            elif review_status == "rejected":
                rejected_count += 1

            upsert_regeneration_request_sync(db=db, batch=batch, item=item, actor_user_id=job.created_by)
            db.add(add_review_item_event(
                item=item,
                previous_status=previous_status,
                review_status=review_status,
                actor_user_id=job.created_by,
                reason=decision_reason,
            ))
        processed_count += len(chunk)
        recalculate_batch_counts(
            batch,
            total_items=initial_total_items,
            approved_count=approved_count,
            rejected_count=rejected_count,
            updated_at=reviewed_at,
        )
        apply_lexicon_job_progress(
            job,
            progress_completed=processed_count,
            progress_total=total,
            current_label=chunk[-1].display_text if chunk else None,
        )
        db.commit()

    return {
        "batch_id": str(batch_id),
        "processed_count": processed_count,
        "approved_count": batch.approved_count,
        "rejected_count": batch.rejected_count,
        "pending_count": batch.pending_count,
        "failed_count": 0,
        "scope": scope,
        "review_status": review_status,
    }


@celery_app.task(bind=True, name="run_lexicon_import_db")
def run_lexicon_import_db(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            import_db = _import_db_module()
            row_summary = dict(request_payload.get("row_summary") or {})
            total_rows = int(row_summary.get("row_count") or 0)

            def _row_label(row: dict[str, Any], *, default_prefix: str, completed_rows: int, total_rows: int) -> str | None:
                explicit_label = str(row.get("_progress_label") or "").strip()
                if explicit_label:
                    entry_label = str(
                        row.get("display_form")
                        or row.get("display_text")
                        or row.get("word")
                        or row.get("normalized_form")
                        or row.get("entry_id")
                        or ""
                    ).strip()
                    return f"{explicit_label}: {entry_label}" if entry_label and entry_label not in explicit_label else explicit_label
                entry_label = str(
                    row.get("display_form")
                    or row.get("display_text")
                    or row.get("word")
                    or row.get("normalized_form")
                    or row.get("entry_id")
                    or ""
                ).strip()
                if not entry_label:
                    return default_prefix
                return f"{default_prefix} {completed_rows}/{total_rows}: {entry_label}" if total_rows > 0 else f"{default_prefix}: {entry_label}"

            result_payload = import_db.run_import_file(
                request_payload["input_path"],
                source_type=request_payload["source_type"],
                source_reference=request_payload.get("source_reference"),
                language=request_payload.get("language", "en"),
                conflict_mode=request_payload.get("conflict_mode"),
                error_mode=request_payload.get("error_mode", "fail_fast"),
                preflight_progress_callback=lambda row, completed_rows, callback_total_rows: (
                    apply_lexicon_job_progress(
                        job,
                        progress_completed=0,
                        progress_total=callback_total_rows or total_rows,
                        current_label=_row_label(
                            row,
                            default_prefix="Validating",
                            completed_rows=completed_rows,
                            total_rows=callback_total_rows or total_rows,
                        ),
                    ),
                    db.commit(),
                ),
                progress_callback=lambda row, completed_rows, total_rows: (
                    apply_lexicon_job_progress(
                        job,
                        progress_completed=completed_rows,
                        progress_total=total_rows,
                        current_label=_row_label(
                            row,
                            default_prefix="Importing",
                            completed_rows=completed_rows,
                            total_rows=total_rows,
                        ),
                    ),
                    db.commit(),
                ),
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_jsonl_materialize")
def run_lexicon_jsonl_materialize(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = materialize_jsonl_review_outputs(
                artifact_path=Path(request_payload["artifact_path"]),
                decisions_path=Path(request_payload["decisions_path"]),
                output_dir=Path(request_payload["output_dir"]),
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_compiled_materialize")
def run_lexicon_compiled_materialize(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = materialize_compiled_review_batch(
                db,
                batch_id=uuid.UUID(request_payload["batch_id"]),
                output_dir=Path(request_payload["output_dir"]),
                settings=settings,
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_compiled_review_bulk_update")
def run_lexicon_compiled_review_bulk_update(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = process_compiled_review_bulk_job(
                db,
                job=job,
                batch_id=uuid.UUID(request_payload["batch_id"]),
                review_status=str(request_payload["review_status"]),
                decision_reason=request_payload.get("decision_reason"),
                scope=str(request_payload.get("scope") or "all_pending"),
                chunk_size=int(request_payload.get("chunk_size") or BULK_REVIEW_CHUNK_SIZE),
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}
