import uuid

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.word_lists import ImportJobResponse, _create_import_job_from_upload, _to_import_job_response
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
    return [_to_import_job_response(row) for row in rows]


@router.get("/{import_id}", response_model=ImportJobResponse)
async def get_import(
    import_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    row = (
        await db.execute(
            select(ImportJob).where(
                ImportJob.id == import_id,
                ImportJob.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Import not found")
    return _to_import_job_response(row)
