import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.services.source_imports import (
    EpubTextExtractor,
    fetch_import_matcher_sync,
    get_or_create_import_source_sync,
    sync_job_with_source,
    upsert_import_source_entries_sync,
)

logger = get_logger(__name__)
settings = get_settings()
sync_engine = create_engine(settings.database_url_sync)


def _import_source_lock_key(import_source_id: uuid.UUID) -> int:
    return import_source_id.int & ((1 << 63) - 1)


def _acquire_import_source_lock(db: Session, import_source_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_lock(:key)"),
        {"key": _import_source_lock_key(import_source_id)},
    )


def _release_import_source_lock(db: Session, import_source_id: uuid.UUID) -> None:
    db.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": _import_source_lock_key(import_source_id)},
    )


def _cleanup_uploaded_file(file_path: str, import_id: str) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError as cleanup_error:
        logger.warning(
            "Failed to clean up uploaded file",
            import_id=import_id,
            path=file_path,
            error=str(cleanup_error),
        )


def _mark_linked_jobs(db: Session, import_source: ImportSource) -> None:
    linked_jobs = db.execute(
        select(ImportJob).where(ImportJob.import_source_id == import_source.id)
    ).scalars().all()
    for job in linked_jobs:
        sync_job_with_source(job, import_source)
        if import_source.status in {"completed", "failed"}:
            job.completed_at = datetime.now(timezone.utc)


@celery_app.task(bind=True, name="process_source_import", queue="imports")
def process_source_import(self, job_id: str, user_id: str, file_path: str) -> dict:
    job_uuid = uuid.UUID(job_id)
    uuid.UUID(user_id)
    lock_acquired = False

    with Session(sync_engine) as db:
        job = db.execute(select(ImportJob).where(ImportJob.id == job_uuid)).scalar_one_or_none()
        if job is None:
            _cleanup_uploaded_file(file_path, job_id)
            return {"status": "failed", "error": "Import job not found"}

        import_source = get_or_create_import_source_sync(
            db,
            source_type="epub",
            source_hash_sha256=job.source_hash,
        )
        job.import_source_id = import_source.id
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            _acquire_import_source_lock(db, import_source.id)
            lock_acquired = True
            import_source = db.execute(
                select(ImportSource).where(ImportSource.id == import_source.id)
            ).scalar_one()

            if import_source.status == "completed":
                logger.info(
                    "source_import_reused_completed_cache",
                    job_id=job_id,
                    import_source_id=str(import_source.id),
                )
                sync_job_with_source(job, import_source)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return {"status": "completed", "matched_entry_count": import_source.matched_entry_count}

            logger.info(
                "source_import_extraction_started",
                job_id=job_id,
                import_source_id=str(import_source.id),
            )
            import_source.status = "processing"
            import_source.error_message = None
            db.commit()

            extractor = EpubTextExtractor()
            metadata, chunks = extractor.extract_metadata_and_chunks(file_path)
            matcher, _, learner_catalog = fetch_import_matcher_sync(db)
            matched_entries = matcher.match_chunks(chunks)

            import_source.title = metadata.title
            import_source.author = metadata.author
            import_source.language = metadata.language
            import_source.source_identifier = metadata.source_identifier
            import_source.published_year = metadata.published_year
            import_source.isbn = metadata.isbn
            import_source.matched_entry_count = len(matched_entries)
            import_source.status = "completed"
            import_source.processed_at = datetime.now(timezone.utc)
            import_source.error_message = None

            upsert_import_source_entries_sync(
                db,
                import_source_id=import_source.id,
                matched_entries=matched_entries,
                learner_catalog=learner_catalog,
            )
            _mark_linked_jobs(db, import_source)
            db.commit()
            return {"status": "completed", "matched_entry_count": import_source.matched_entry_count}
        except Exception as exc:
            logger.error("source_import_failed", job_id=job_id, error=str(exc))
            import_source.status = "failed"
            import_source.error_message = str(exc)
            import_source.processed_at = datetime.now(timezone.utc)
            _mark_linked_jobs(db, import_source)
            db.commit()
            return {"status": "failed", "error": str(exc)}
        finally:
            if lock_acquired:
                _release_import_source_lock(db, import_source.id)
                db.commit()
            _cleanup_uploaded_file(file_path, job_id)


@celery_app.task(bind=True, name="extract_epub_vocabulary", queue="imports")
def extract_epub_vocabulary(self, import_id: str, user_id: str, file_path: str) -> dict:
    return process_source_import(import_id, user_id, file_path)


@celery_app.task(bind=True, name="process_word_list_import", queue="imports")
def process_word_list_import(self, job_id: str, user_id: str, file_path: str) -> dict:
    return process_source_import(job_id, user_id, file_path)
