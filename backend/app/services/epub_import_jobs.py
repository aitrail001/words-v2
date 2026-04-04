import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.uploads import resolve_upload_dir
from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.user import User
from app.services.source_imports import SOURCE_TYPE_EPUB, create_import_job, get_or_create_import_source
from app.tasks.epub_processing import process_word_list_import

logger = get_logger(__name__)
settings = get_settings()
UPLOAD_DIR = resolve_upload_dir()


def _is_completed_cache_available(import_source: ImportSource) -> bool:
    return import_source.status == "completed" and import_source.deleted_at is None


async def _count_active_imports_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(ImportJob)
                .where(
                    ImportJob.user_id == user_id,
                    ImportJob.status.in_(("queued", "processing")),
                )
            )
        ).scalar_one()
    )


async def enqueue_epub_import_upload(
    *,
    db: AsyncSession,
    actor_user: User,
    file: UploadFile,
    list_name: str | None,
    list_description: str | None,
    job_origin: str = "user_import",
    import_batch_id: uuid.UUID | None = None,
    enforce_active_import_limit: bool = True,
) -> tuple[ImportJob, ImportSource, bool]:
    user_id = actor_user.id
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only .epub files are supported")

    if enforce_active_import_limit:
        active_import_count = await _count_active_imports_for_user(db, user_id=user_id)
        if active_import_count >= settings.max_active_imports_per_user:
            raise HTTPException(status_code=429, detail="Too many active imports")

    file_id = uuid.uuid4()
    safe_name = Path(filename).name
    saved_path = UPLOAD_DIR / f"{file_id}-{safe_name}"

    hasher = hashlib.sha256()
    try:
        with saved_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                out.write(chunk)
    finally:
        await file.close()

    source_hash = hasher.hexdigest()
    import_source = await get_or_create_import_source(
        db,
        source_type=SOURCE_TYPE_EPUB,
        source_hash_sha256=source_hash,
    )
    job = await create_import_job(
        db,
        user_id=user_id,
        import_source=import_source,
        source_filename=safe_name,
        list_name=(list_name or Path(safe_name).stem).strip() or "Imported list",
        list_description=list_description,
        job_origin=job_origin,
        import_batch_id=import_batch_id,
    )

    if _is_completed_cache_available(import_source):
        saved_path.unlink(missing_ok=True)
        return job, import_source, True

    try:
        process_word_list_import.delay(str(job.id), str(user_id), str(saved_path))
    except Exception as exc:
        logger.error("Failed to enqueue source import task", import_job_id=str(job.id), error=str(exc))
        saved_path.unlink(missing_ok=True)
        job.status = "failed"
        job.error_count += 1
        job.error_message = "Failed to queue import task"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=503, detail="Import queue is unavailable")

    return job, import_source, False
