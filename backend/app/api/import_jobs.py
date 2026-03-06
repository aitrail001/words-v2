import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.import_job import ImportJob
from app.models.user import User

router = APIRouter()


class ImportJobResponse(BaseModel):
    id: str
    user_id: str
    book_id: str | None
    word_list_id: str | None
    status: str
    source_filename: str
    source_hash: str
    list_name: str
    list_description: str | None
    total_items: int
    processed_items: int
    created_count: int
    skipped_count: int
    not_found_count: int
    not_found_words: list[str] | None
    error_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


def _to_import_job_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=str(job.id),
        user_id=str(job.user_id),
        book_id=str(job.book_id) if job.book_id else None,
        word_list_id=str(job.word_list_id) if job.word_list_id else None,
        status=job.status,
        source_filename=job.source_filename,
        source_hash=job.source_hash,
        list_name=job.list_name,
        list_description=job.list_description,
        total_items=job.total_items,
        processed_items=job.processed_items,
        created_count=job.created_count,
        skipped_count=job.skipped_count,
        not_found_count=job.not_found_count,
        not_found_words=job.not_found_words,
        error_count=job.error_count,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


async def _get_job_for_user(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ImportJob:
    result = await db.execute(
        select(ImportJob).where(ImportJob.id == job_id, ImportJob.user_id == user_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await _get_job_for_user(job_id, current_user.id, db)
    return _to_import_job_response(job)


@router.get("/{job_id}/events")
async def stream_import_job_events(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await _get_job_for_user(job_id, current_user.id, db)
    event_type = "completed" if job.status in {"completed", "failed"} else "progress"
    payload = _to_import_job_response(job).model_dump(mode="json")
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()

    async def event_stream():
        yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
