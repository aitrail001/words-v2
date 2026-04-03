from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lexicon_job import LexiconJob

ACTIVE_JOB_STATUSES = {"queued", "running", "cancel_requested"}
INPUT_SERIALIZED_JOB_TYPES = {"import_db", "voice_import_db"}


class ActiveLexiconJobConflictError(RuntimeError):
    def __init__(self, *, job: LexiconJob, job_type: str, source_identity: str) -> None:
        self.job = job
        self.job_type = job_type
        self.source_identity = source_identity
        super().__init__(
            f"An active {job_type} job already exists for source '{source_identity}' "
            f"(job {job.id}, status {job.status}). Wait for it to finish before starting another import "
            "for the same source."
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_active_lexicon_job_for_source_reference(
    db: AsyncSession,
    *,
    job_type: str,
    source_reference: str,
) -> LexiconJob | None:
    normalized_source_reference = source_reference.strip()
    if not normalized_source_reference:
        return None
    result = await db.execute(
        select(LexiconJob)
        .where(LexiconJob.job_type == job_type)
        .where(LexiconJob.status.in_(ACTIVE_JOB_STATUSES))
        .where(LexiconJob.request_payload["source_reference"].as_string() == normalized_source_reference)
        .order_by(LexiconJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_or_reuse_lexicon_job(
    db: AsyncSession,
    *,
    created_by: uuid.UUID | None,
    job_type: str,
    target_key: str,
    request_payload: dict[str, Any],
) -> tuple[LexiconJob, bool]:
    source_reference = str(request_payload.get("source_reference") or "").strip()
    source_identity = str(request_payload.get("input_path") or source_reference or target_key).strip()

    result = await db.execute(
        select(LexiconJob)
        .where(LexiconJob.job_type == job_type)
        .where(LexiconJob.target_key == target_key)
        .where(LexiconJob.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(LexiconJob.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        if job_type in INPUT_SERIALIZED_JOB_TYPES:
            raise ActiveLexiconJobConflictError(
                job=existing,
                job_type=job_type,
                source_identity=source_identity,
            )
        return existing, False

    job = LexiconJob(
        created_by=created_by,
        job_type=job_type,
        target_key=target_key,
        request_payload=request_payload,
    )
    db.add(job)
    await db.flush()
    return job, True


async def get_lexicon_job(db: AsyncSession, job_id: uuid.UUID) -> LexiconJob | None:
    result = await db.execute(select(LexiconJob).where(LexiconJob.id == job_id))
    return result.scalar_one_or_none()


def apply_lexicon_job_started(job: LexiconJob) -> None:
    if job.status == "cancel_requested":
        return
    job.status = "running"
    job.started_at = job.started_at or _now()


def apply_lexicon_job_progress(
    job: LexiconJob,
    *,
    progress_completed: int,
    progress_total: int,
    current_label: str | None,
) -> None:
    if job.status == "queued":
        apply_lexicon_job_started(job)
    job.progress_completed = max(int(job.progress_completed or 0), int(progress_completed))
    job.progress_total = max(int(job.progress_total or 0), int(progress_total))
    job.progress_current_label = current_label


def apply_lexicon_job_completed(job: LexiconJob, *, result_payload: dict[str, Any]) -> None:
    job.status = "completed"
    job.result_payload = result_payload
    job.error_message = None
    job.completed_at = _now()
    if job.progress_total and job.progress_completed < job.progress_total:
        job.progress_completed = job.progress_total


def apply_lexicon_job_failed(job: LexiconJob, error_message: str) -> None:
    job.status = "failed"
    job.error_message = error_message
    job.completed_at = _now()


def apply_lexicon_job_cancel_requested(job: LexiconJob) -> None:
    if job.status in {"completed", "failed", "cancelled"}:
        return
    job.status = "cancel_requested"
    job.error_message = None


def apply_lexicon_job_cancelled(job: LexiconJob) -> None:
    job.status = "cancelled"
    job.error_message = None
    job.completed_at = _now()
