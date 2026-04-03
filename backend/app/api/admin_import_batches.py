import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models.import_batch import ImportBatch
from app.models.import_job import ImportJob
from app.models.user import User
from app.services.admin_import_sources import get_import_batch_summary, list_import_batches
from app.services.epub_import_jobs import enqueue_epub_import_upload

router = APIRouter()
settings = get_settings()


@router.post("/epub")
async def create_epub_import_batch(
    files: list[UploadFile] = File(...),
    batch_name: str | None = Form(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="At least one EPUB file is required")
    max_files = max(1, settings.max_active_admin_preimports_per_request)
    if len(files) > max_files:
        raise HTTPException(status_code=400, detail=f"Too many files in batch (max {max_files})")

    batch = ImportBatch(
        created_by_user_id=current_user.id,
        batch_type="epub_preimport",
        name=(batch_name or "").strip() or None,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    jobs: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for file in files:
        source_filename = (file.filename or "").strip() or "unknown.epub"
        try:
            job, _, completed_from_cache = await enqueue_epub_import_upload(
                db=db,
                actor_user=current_user,
                file=file,
                list_name=None,
                list_description=None,
                job_origin="admin_preimport",
                import_batch_id=batch.id,
                enforce_active_import_limit=False,
            )
            jobs.append(
                {
                    "id": str(job.id),
                    "status": job.status,
                    "source_filename": job.source_filename,
                    "import_source_id": str(job.import_source_id) if job.import_source_id else None,
                    "from_cache": completed_from_cache,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                }
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            failures.append({"source_filename": source_filename, "error": detail})
        except Exception:
            failures.append({"source_filename": source_filename, "error": "Failed to enqueue import"})

    summary = await get_import_batch_summary(db, batch_id=batch.id)
    return {
        "batch": summary,
        "jobs": jobs,
        "failures": failures,
    }


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
