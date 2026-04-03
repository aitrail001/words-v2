import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.word_lists import (
    CreateWordListFromImportRequest,
    ImportJobResponse,
    ReviewEntriesResponse,
    WordListResponse,
    _assert_unique_word_list_name,
    _get_import_job_for_user,
    _hydrate_import_jobs_with_source_details,
    _to_import_job_response,
    _to_word_list_response,
)
from app.core.database import get_db
from app.models.import_job import ImportJob
from app.models.user import User
from app.services.source_imports import EntryRef, create_word_list_from_entries, fetch_review_entries

router = APIRouter()


class BulkDeleteImportJobsRequest(BaseModel):
    job_ids: list[uuid.UUID]


@router.get("", response_model=list[ImportJobResponse])
async def list_import_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    status_view: str = Query(default="all"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportJobResponse]:
    query = select(ImportJob).where(ImportJob.user_id == current_user.id)
    if status_view == "active":
        query = query.where(ImportJob.status.in_(("queued", "processing")))
    elif status_view == "history":
        query = query.where(ImportJob.status.in_(("completed", "failed")))
    elif status_view != "all":
        raise HTTPException(status_code=400, detail="Unsupported status view")
    jobs = (
        await db.execute(
            query
            .order_by(ImportJob.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    jobs = await _hydrate_import_jobs_with_source_details(db, list(jobs))
    return [_to_import_job_response(job) for job in jobs]


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    await _hydrate_import_jobs_with_source_details(db, [job])
    return _to_import_job_response(job)


@router.delete("/{job_id}", status_code=204)
async def delete_import_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    if job.status not in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail="Only completed or failed import jobs can be deleted")
    await db.delete(job)
    await db.commit()


@router.delete("", status_code=204)
async def bulk_delete_import_jobs(
    request: BulkDeleteImportJobsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.job_ids:
        return
    jobs = (
        await db.execute(
            select(ImportJob).where(
                ImportJob.user_id == current_user.id,
                ImportJob.id.in_(request.job_ids),
            )
        )
    ).scalars().all()
    active_job = next((job for job in jobs if job.status not in {"completed", "failed"}), None)
    if active_job is not None:
        raise HTTPException(status_code=409, detail="Only completed or failed import jobs can be deleted")
    for job in jobs:
        await db.delete(job)
    await db.commit()


@router.get("/{job_id}/entries", response_model=ReviewEntriesResponse)
async def list_import_job_entries(
    job_id: uuid.UUID,
    q: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    phrase_kind: str | None = Query(default=None),
    sort: str = Query(default="book_frequency"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewEntriesResponse:
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    if job.import_source_id is None:
        raise HTTPException(status_code=409, detail="Import source is not ready")
    total, items = await fetch_review_entries(
        db,
        import_source_id=job.import_source_id,
        q=q,
        entry_type=entry_type,
        phrase_kind=phrase_kind,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return ReviewEntriesResponse(total=total, items=items)


@router.post("/{job_id}/word-lists", response_model=WordListResponse, status_code=201)
async def create_word_list_from_import_job(
    job_id: uuid.UUID,
    request: CreateWordListFromImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListResponse:
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    await _assert_unique_word_list_name(db, user_id=current_user.id, name=request.name)
    try:
        word_list = await create_word_list_from_entries(
            db,
            user_id=current_user.id,
            job=job,
            name=request.name.strip(),
            description=request.description,
            selected_entries=[
                EntryRef(entry_type=entry.entry_type, entry_id=entry.entry_id)
                for entry in request.selected_entries
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_word_list_response(word_list)


@router.get("/{job_id}/events")
async def stream_import_job_events(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    event_type = "completed" if job.status in {"completed", "failed"} else "progress"
    payload = _to_import_job_response(job).model_dump(mode="json")
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()

    async def event_stream():
        yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
