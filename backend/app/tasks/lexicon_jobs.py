from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.models.lexicon_job import LexiconJob
from app.services.lexicon_compiled_reviews import materialize_compiled_review_batch
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


@celery_app.task(bind=True, name="run_lexicon_import_db")
def run_lexicon_import_db(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            import_db = _import_db_module()
            result_payload = import_db.run_import_file(
                request_payload["input_path"],
                source_type=request_payload["source_type"],
                source_reference=request_payload.get("source_reference"),
                language=request_payload.get("language", "en"),
                progress_callback=lambda row, completed_rows, total_rows: (
                    apply_lexicon_job_progress(
                        job,
                        progress_completed=completed_rows,
                        progress_total=total_rows,
                        current_label=str(
                            row.get("display_form")
                            or row.get("display_text")
                            or row.get("word")
                            or row.get("normalized_form")
                            or row.get("entry_id")
                            or ""
                        ).strip()
                        or None,
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
