import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.word_lists import (
    CreateWordListFromImportRequest,
    ImportJobResponse,
    ReviewEntriesResponse,
    WordListResponse,
    _get_import_job_for_user,
    _to_import_job_response,
    _to_word_list_response,
)
from app.core.database import get_db
from app.models.import_job import ImportJob
from app.models.user import User
from app.services.source_imports import EntryRef, create_word_list_from_entries, fetch_review_entries

router = APIRouter()


@router.get("", response_model=list[ImportJobResponse])
async def list_import_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportJobResponse]:
    jobs = (
        await db.execute(
            select(ImportJob)
            .where(ImportJob.user_id == current_user.id)
            .order_by(ImportJob.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_to_import_job_response(job) for job in jobs]


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await _get_import_job_for_user(db, job_id=job_id, user_id=current_user.id)
    return _to_import_job_response(job)


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
