import uuid
from types import SimpleNamespace

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.import_batch import ImportBatch
from app.models.import_job import ImportJob
from app.models.user import User
from app.services.admin_import_sources import get_import_batch_summary, list_import_batches
from app.services.epub_import_jobs import enqueue_epub_import_upload

router = APIRouter()
settings = get_settings()
logger = get_logger(__name__)


class CreateAdminImportBatchRequest(BaseModel):
    batch_name: str | None = Field(default=None, max_length=255)


async def _create_epub_batch_record(
    *,
    db: AsyncSession,
    current_user: User,
    batch_name: str | None,
) -> ImportBatch:
    normalized_batch_name = (batch_name or "").strip() or None
    batch = ImportBatch(
        created_by_user_id=current_user.id,
        batch_type="epub_preimport",
        name=normalized_batch_name,
    )
    db.add(batch)
    try:
        await db.commit()
        await db.refresh(batch)
    except Exception as exc:
        await db.rollback()
        logger.error("admin_epub_batch_create_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Failed to initialize import batch") from exc
    return batch


def _serialize_job(job: ImportJob, *, completed_from_cache: bool) -> dict[str, object]:
    return {
        "id": str(job.id),
        "status": job.status,
        "source_filename": job.source_filename,
        "import_source_id": str(job.import_source_id) if job.import_source_id else None,
        "from_cache": completed_from_cache,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }


def _build_fallback_summary(
    *,
    batch: ImportBatch,
    jobs: list[dict[str, object]],
    failures: list[dict[str, str]],
) -> dict[str, object]:
    completed_jobs = sum(1 for job in jobs if job["status"] == "completed")
    failed_jobs = len(failures) + sum(1 for job in jobs if job["status"] == "failed")
    active_jobs = sum(1 for job in jobs if job["status"] in {"queued", "processing"})
    return {
        "id": str(batch.id),
        "created_by_user_id": str(batch.created_by_user_id),
        "batch_type": "epub_preimport",
        "name": batch.name,
        "created_at": batch.created_at,
        "total_jobs": len(jobs),
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "active_jobs": active_jobs,
    }


async def _enqueue_files_into_batch(
    *,
    db: AsyncSession,
    current_user: User,
    batch: ImportBatch,
    files: list[UploadFile],
) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one EPUB file is required")
    max_files = max(1, settings.max_active_admin_preimports_per_request)
    if len(files) > max_files:
        raise HTTPException(status_code=400, detail=f"Too many files in batch (max {max_files})")
    actor = SimpleNamespace(id=current_user.id)

    jobs: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for file in files:
        source_filename = (file.filename or "").strip() or "unknown.epub"
        try:
            job, _, completed_from_cache = await enqueue_epub_import_upload(
                db=db,
                actor_user=actor,  # keep stable id even if rollback expires ORM-bound current_user
                file=file,
                list_name=None,
                list_description=None,
                job_origin="admin_preimport",
                import_batch_id=batch.id,
                enforce_active_import_limit=False,
            )
            jobs.append(_serialize_job(job, completed_from_cache=completed_from_cache))
        except HTTPException as exc:
            await db.rollback()
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            failures.append({"source_filename": source_filename, "error": detail})
        except Exception:
            await db.rollback()
            logger.exception(
                "admin_epub_batch_enqueue_failed",
                batch_id=str(batch.id),
                source_filename=source_filename,
            )
            failures.append({"source_filename": source_filename, "error": "Failed to enqueue import"})

    try:
        summary = await get_import_batch_summary(db, batch_id=batch.id)
    except Exception as exc:
        logger.exception("admin_epub_batch_summary_failed", batch_id=str(batch.id), error=str(exc))
        summary = _build_fallback_summary(
            batch=batch,
            jobs=jobs,
            failures=failures,
        )
    return {
        "batch": summary,
        "jobs": jobs,
        "failures": failures,
    }


@router.post("")
async def create_import_batch(
    payload: CreateAdminImportBatchRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = await _create_epub_batch_record(
        db=db,
        current_user=current_user,
        batch_name=payload.batch_name,
    )
    return _build_fallback_summary(
        batch=batch,
        jobs=[],
        failures=[],
    )


@router.post("/{batch_id}/epub")
async def add_epub_files_to_batch(
    batch_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = (await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    if batch.batch_type != "epub_preimport":
        raise HTTPException(status_code=400, detail="Import batch does not accept EPUB files")
    return await _enqueue_files_into_batch(
        db=db,
        current_user=current_user,
        batch=batch,
        files=files,
    )


@router.post("/epub")
async def create_epub_import_batch(
    files: list[UploadFile] = File(...),
    batch_name: str | None = Form(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = await _create_epub_batch_record(
        db=db,
        current_user=current_user,
        batch_name=batch_name,
    )
    return await _enqueue_files_into_batch(
        db=db,
        current_user=current_user,
        batch=batch,
        files=files,
    )


@router.get("")
async def list_batches(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total, items = await list_import_batches(db, limit=limit, offset=offset)
    return {"total": total, "items": items}


@router.get("/{batch_id}")
async def get_batch(
    batch_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    summary = await get_import_batch_summary(db, batch_id=batch_id)
    return summary


@router.get("/{batch_id}/jobs")
async def get_batch_jobs(
    batch_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = (await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")

    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ImportJob)
                .where(ImportJob.import_batch_id == batch_id)
            )
        ).scalar_one()
    )
    jobs = (
        await db.execute(
            select(ImportJob)
            .where(ImportJob.import_batch_id == batch_id)
            .order_by(ImportJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return {
        "total": total,
        "items": [
            {
                "id": str(job.id),
                "status": job.status,
                "source_filename": job.source_filename,
                "import_source_id": str(job.import_source_id) if job.import_source_id else None,
                "job_origin": job.job_origin,
                "from_cache": bool(job.status == "completed" and job.started_at is None),
                "matched_entry_count": job.matched_entry_count,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
            }
            for job in jobs
        ],
    }
