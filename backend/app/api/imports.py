import uuid

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.word_lists import (
    ImportJobResponse,
    _create_import_job_from_upload,
    _get_import_job_for_user,
    _hydrate_import_jobs_with_source_details,
    _to_import_job_response,
)
from app.core.database import get_db
from app.models.import_job import ImportJob
from app.models.user import User

router = APIRouter()


@router.post("", response_model=ImportJobResponse)
async def create_import(
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    return await _create_import_job_from_upload(
        db=db,
        user=current_user,
        file=file,
        list_name=None,
        list_description=None,
        response=response,
    )


@router.get("", response_model=list[ImportJobResponse])
async def list_imports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportJobResponse]:
    rows = (
        await db.execute(
            select(ImportJob)
            .where(ImportJob.user_id == current_user.id)
            .order_by(ImportJob.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    rows = await _hydrate_import_jobs_with_source_details(db, list(rows))
    return [_to_import_job_response(row) for row in rows]


@router.get("/{import_id}", response_model=ImportJobResponse)
async def get_import(
    import_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    row = await _get_import_job_for_user(db, job_id=import_id, user_id=current_user.id)
    await _hydrate_import_jobs_with_source_details(db, [row])
    return _to_import_job_response(row)
