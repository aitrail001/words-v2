import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.api.word_lists import _hydrate_import_jobs_with_source_details, _to_import_job_response
from app.core.database import get_db
from app.models.import_job import ImportJob
from app.models.user import User

router = APIRouter()


@router.get("/{job_id}")
async def get_admin_import_job(
    job_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    await _hydrate_import_jobs_with_source_details(db, [job])
    return _to_import_job_response(job).model_dump(mode="json")
