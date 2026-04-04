import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import Select, and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.import_batch import ImportBatch
from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.user import User

DELETE_MODE_CACHE_ONLY = "cache_only"
DELETE_MODE_CACHE_ONLY_AND_DELETE_ORPHAN_JOBS = "cache_only_and_delete_orphan_jobs"


@dataclass(frozen=True)
class AdminImportSourceDeleteResult:
    source_id: uuid.UUID
    deleted_entry_count: int
    deleted_orphan_job_count: int


def import_job_from_cache_expr() -> case:
    return case((and_(ImportJob.status == "completed", ImportJob.started_at.is_(None)), True), else_=False)


def _build_sources_base_query(*, q: str | None, status_filter: str | None) -> Select:
    query = select(ImportSource)
    if q:
        lowered = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(func.coalesce(ImportSource.title, "")).like(lowered),
                func.lower(func.coalesce(ImportSource.author, "")).like(lowered),
                func.lower(func.coalesce(ImportSource.publisher, "")).like(lowered),
                func.lower(func.coalesce(ImportSource.isbn, "")).like(lowered),
            )
        )
    if status_filter and status_filter != "all":
        if status_filter == "deleted":
            query = query.where(ImportSource.deleted_at.is_not(None))
        else:
            query = query.where(ImportSource.status == status_filter)
    return query


async def list_admin_import_sources(
    db: AsyncSession,
    *,
    q: str | None,
    status_filter: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    base_query = _build_sources_base_query(q=q, status_filter=status_filter)
    base_subquery = base_query.subquery()
    total = int((await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar_one())

    processing_jobs = (
        select(
            ImportJob.import_source_id.label("import_source_id"),
            ImportJob.id.label("job_id"),
            ImportJob.user_id.label("user_id"),
            ImportJob.source_filename.label("source_filename"),
            ImportJob.started_at.label("started_at"),
            ImportJob.completed_at.label("completed_at"),
            func.coalesce(ImportJob.started_at, ImportJob.created_at).label("sort_started_at"),
            func.row_number()
            .over(
                partition_by=ImportJob.import_source_id,
                order_by=func.coalesce(ImportJob.started_at, ImportJob.created_at).asc(),
            )
            .label("rn"),
        )
        .where(
            ImportJob.import_source_id.is_not(None),
            ImportJob.started_at.is_not(None),
        )
        .subquery()
    )
    first_processing = select(processing_jobs).where(processing_jobs.c.rn == 1).subquery()

    latest_completed_processing_jobs = (
        select(
            ImportJob.import_source_id.label("import_source_id"),
            ImportJob.started_at.label("started_at"),
            ImportJob.completed_at.label("completed_at"),
            func.row_number()
            .over(
                partition_by=ImportJob.import_source_id,
                order_by=ImportJob.started_at.desc(),
            )
            .label("rn"),
        )
        .where(
            ImportJob.import_source_id.is_not(None),
            ImportJob.started_at.is_not(None),
            ImportJob.completed_at.is_not(None),
            ImportJob.status == "completed",
        )
        .subquery()
    )
    latest_completed_processing = (
        select(latest_completed_processing_jobs)
        .where(latest_completed_processing_jobs.c.rn == 1)
        .subquery()
    )

    cache_hit_jobs = (
        select(
            ImportJob.import_source_id.label("import_source_id"),
            ImportJob.id.label("job_id"),
            ImportJob.user_id.label("user_id"),
            ImportJob.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=ImportJob.import_source_id,
                order_by=ImportJob.created_at.desc(),
            )
            .label("rn"),
        )
        .where(
            ImportJob.import_source_id.is_not(None),
            ImportJob.status == "completed",
            ImportJob.started_at.is_(None),
        )
        .subquery()
    )
    last_cache_hit = select(cache_hit_jobs).where(cache_hit_jobs.c.rn == 1).subquery()

    usage_agg = (
        select(
            ImportJob.import_source_id.label("import_source_id"),
            func.count().label("total_jobs"),
            func.sum(
                case(
                    (and_(ImportJob.status == "completed", ImportJob.started_at.is_(None)), 1),
                    else_=0,
                )
            ).label("cache_hit_count"),
        )
        .where(ImportJob.import_source_id.is_not(None))
        .group_by(ImportJob.import_source_id)
        .subquery()
    )
    entry_counts = (
        select(
            ImportSourceEntry.import_source_id.label("import_source_id"),
            func.sum(case((ImportSourceEntry.entry_type == "word", 1), else_=0)).label("word_entry_count"),
            func.sum(case((ImportSourceEntry.entry_type == "phrase", 1), else_=0)).label("phrase_entry_count"),
        )
        .group_by(ImportSourceEntry.import_source_id)
        .subquery()
    )

    first_user = aliased(User)
    last_user = aliased(User)

    sort_map = {
        "title": func.lower(func.coalesce(ImportSource.title, "")),
        "author": func.lower(func.coalesce(ImportSource.author, "")),
        "status": ImportSource.status,
        "matched_entry_count": ImportSource.matched_entry_count,
        "first_imported_at": first_processing.c.sort_started_at,
        "cache_hit_count": usage_agg.c.cache_hit_count,
        "last_reused_at": last_cache_hit.c.created_at,
        "processed_at": ImportSource.processed_at,
        "created_at": ImportSource.created_at,
    }
    sort_column = sort_map.get(sort, ImportSource.processed_at)
    order_column = desc(sort_column) if order == "desc" else sort_column

    query = (
        select(
            ImportSource,
            usage_agg.c.total_jobs,
            usage_agg.c.cache_hit_count,
            entry_counts.c.word_entry_count,
            entry_counts.c.phrase_entry_count,
            first_processing.c.sort_started_at.label("first_imported_at"),
            first_processing.c.started_at.label("first_started_at"),
            first_processing.c.completed_at.label("first_completed_at"),
            first_processing.c.source_filename.label("source_filename"),
            first_processing.c.user_id.label("first_imported_by_user_id"),
            first_user.email.label("first_imported_by_email"),
            first_user.role.label("first_imported_by_role"),
            latest_completed_processing.c.started_at.label("duration_started_at"),
            latest_completed_processing.c.completed_at.label("duration_completed_at"),
            last_cache_hit.c.created_at.label("last_reused_at"),
            last_cache_hit.c.user_id.label("last_reused_by_user_id"),
            last_user.email.label("last_reused_by_email"),
            last_user.role.label("last_reused_by_role"),
        )
        .select_from(base_subquery.join(ImportSource, ImportSource.id == base_subquery.c.id))
        .outerjoin(usage_agg, usage_agg.c.import_source_id == ImportSource.id)
        .outerjoin(entry_counts, entry_counts.c.import_source_id == ImportSource.id)
        .outerjoin(first_processing, first_processing.c.import_source_id == ImportSource.id)
        .outerjoin(first_user, first_user.id == first_processing.c.user_id)
        .outerjoin(latest_completed_processing, latest_completed_processing.c.import_source_id == ImportSource.id)
        .outerjoin(last_cache_hit, last_cache_hit.c.import_source_id == ImportSource.id)
        .outerjoin(last_user, last_user.id == last_cache_hit.c.user_id)
        .order_by(order_column.nullslast(), ImportSource.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = (await db.execute(query)).all()
    items: list[dict[str, object]] = []
    for row in rows:
        source: ImportSource = row[0]
        first_started_at = row.duration_started_at
        first_completed_at = row.duration_completed_at
        processing_duration_seconds = None
        if first_started_at is not None and first_completed_at is not None:
            processing_duration_seconds = max(0.0, (first_completed_at - first_started_at).total_seconds())
        items.append(
            {
                "id": str(source.id),
                "source_type": source.source_type,
                "source_hash_sha256": source.source_hash_sha256,
                "title": source.title,
                "author": source.author,
                "publisher": source.publisher,
                "language": source.language,
                "source_identifier": source.source_identifier,
                "published_year": source.published_year,
                "isbn": source.isbn,
                "status": source.status,
                "matched_entry_count": source.matched_entry_count,
                "word_entry_count": int(row.word_entry_count or 0),
                "phrase_entry_count": int(row.phrase_entry_count or 0),
                "created_at": source.created_at,
                "processed_at": source.processed_at,
                "deleted_at": source.deleted_at,
                "deleted_by_user_id": str(source.deleted_by_user_id) if source.deleted_by_user_id else None,
                "deletion_reason": source.deletion_reason,
                "first_imported_at": row.first_imported_at,
                "first_imported_by_user_id": str(row.first_imported_by_user_id) if row.first_imported_by_user_id else None,
                "first_imported_by_email": row.first_imported_by_email,
                "first_imported_by_role": row.first_imported_by_role,
                "processing_duration_seconds": processing_duration_seconds,
                "source_filename": row.source_filename,
                "total_jobs": int(row.total_jobs or 0),
                "cache_hit_count": int(row.cache_hit_count or 0),
                "last_reused_at": row.last_reused_at,
                "last_reused_by_user_id": str(row.last_reused_by_user_id) if row.last_reused_by_user_id else None,
                "last_reused_by_email": row.last_reused_by_email,
                "last_reused_by_role": row.last_reused_by_role,
            }
        )

    return total, items


async def list_import_source_jobs(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    from_cache: str,
    job_origin: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    from_cache_expr = and_(ImportJob.status == "completed", ImportJob.started_at.is_(None))
    query = (
        select(ImportJob, User.email.label("user_email"), User.role.label("user_role"))
        .outerjoin(User, User.id == ImportJob.user_id)
        .where(ImportJob.import_source_id == source_id)
    )
    if from_cache == "true":
        query = query.where(from_cache_expr)
    elif from_cache == "false":
        query = query.where(~from_cache_expr)
    elif from_cache != "all":
        raise HTTPException(status_code=400, detail="Unsupported from_cache filter")
    if job_origin:
        query = query.where(ImportJob.job_origin == job_origin)

    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
    rows = (
        await db.execute(
            query.order_by(ImportJob.created_at.desc()).offset(offset).limit(limit)
        )
    ).all()

    items: list[dict[str, object]] = []
    for row in rows:
        job: ImportJob = row[0]
        duration = None
        if job.started_at and job.completed_at:
            duration = max(0.0, (job.completed_at - job.started_at).total_seconds())
        items.append(
            {
                "id": str(job.id),
                "user_id": str(job.user_id),
                "user_email": row.user_email,
                "user_role": row.user_role,
                "import_batch_id": str(job.import_batch_id) if job.import_batch_id else None,
                "job_origin": job.job_origin,
                "status": job.status,
                "source_filename": job.source_filename,
                "list_name": job.list_name,
                "matched_entry_count": job.matched_entry_count,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "from_cache": bool(job.status == "completed" and job.started_at is None),
                "processing_duration_seconds": duration,
            }
        )
    return total, items


async def soft_delete_import_source_cache(
    db: AsyncSession,
    *,
    source: ImportSource,
    deleted_by: User,
    delete_mode: str,
    deletion_reason: str | None,
) -> AdminImportSourceDeleteResult:
    if delete_mode not in {DELETE_MODE_CACHE_ONLY, DELETE_MODE_CACHE_ONLY_AND_DELETE_ORPHAN_JOBS}:
        raise HTTPException(status_code=400, detail="Unsupported delete mode")

    entry_count_row = (
        await db.execute(
            select(
                func.count().label("total_entries"),
                func.sum(case((ImportSourceEntry.entry_type == "word", 1), else_=0)).label("word_entries"),
                func.sum(case((ImportSourceEntry.entry_type == "phrase", 1), else_=0)).label("phrase_entries"),
            ).where(ImportSourceEntry.import_source_id == source.id)
        )
    ).one()
    deleted_entry_count = int(entry_count_row.total_entries or 0)
    source_word_count = int(entry_count_row.word_entries or 0)
    source_phrase_count = int(entry_count_row.phrase_entries or 0)

    linked_jobs = (
        await db.execute(select(ImportJob).where(ImportJob.import_source_id == source.id))
    ).scalars().all()
    for job in linked_jobs:
        if job.word_entry_count == 0 and source_word_count > 0:
            job.word_entry_count = source_word_count
        if job.phrase_entry_count == 0 and source_phrase_count > 0:
            job.phrase_entry_count = source_phrase_count

    await db.execute(
        ImportSourceEntry.__table__.delete().where(ImportSourceEntry.import_source_id == source.id)
    )

    source.deleted_at = datetime.now(timezone.utc)
    source.deleted_by_user_id = deleted_by.id
    source.deletion_reason = deletion_reason
    source.status = "deleted"
    source.matched_entry_count = 0
    source.processed_at = datetime.now(timezone.utc)

    deleted_orphan_job_count = 0
    if delete_mode == DELETE_MODE_CACHE_ONLY_AND_DELETE_ORPHAN_JOBS:
        orphan_jobs = (
            await db.execute(
                select(ImportJob).where(
                    ImportJob.import_source_id == source.id,
                    ImportJob.word_list_id.is_(None),
                    ImportJob.job_origin == "admin_preimport",
                )
            )
        ).scalars().all()
        for job in orphan_jobs:
            await db.delete(job)
        deleted_orphan_job_count = len(orphan_jobs)

    await db.commit()
    return AdminImportSourceDeleteResult(
        source_id=source.id,
        deleted_entry_count=deleted_entry_count,
        deleted_orphan_job_count=deleted_orphan_job_count,
    )


async def list_import_batches(
    db: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    total = int((await db.execute(select(func.count()).select_from(ImportBatch))).scalar_one())
    jobs_agg = (
        select(
            ImportJob.import_batch_id.label("import_batch_id"),
            func.count().label("total_jobs"),
            func.sum(case((ImportJob.status == "completed", 1), else_=0)).label("completed_jobs"),
            func.sum(case((ImportJob.status == "failed", 1), else_=0)).label("failed_jobs"),
            func.sum(case((ImportJob.status.in_(("queued", "processing")), 1), else_=0)).label("active_jobs"),
        )
        .where(ImportJob.import_batch_id.is_not(None))
        .group_by(ImportJob.import_batch_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                ImportBatch,
                User.email.label("created_by_email"),
                jobs_agg.c.total_jobs,
                jobs_agg.c.completed_jobs,
                jobs_agg.c.failed_jobs,
                jobs_agg.c.active_jobs,
            )
            .outerjoin(User, User.id == ImportBatch.created_by_user_id)
            .outerjoin(jobs_agg, jobs_agg.c.import_batch_id == ImportBatch.id)
            .order_by(ImportBatch.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = []
    for row in rows:
        batch: ImportBatch = row[0]
        items.append(
            {
                "id": str(batch.id),
                "created_by_user_id": str(batch.created_by_user_id),
                "created_by_email": row.created_by_email,
                "batch_type": batch.batch_type,
                "name": batch.name,
                "created_at": batch.created_at,
                "total_jobs": int(row.total_jobs or 0),
                "completed_jobs": int(row.completed_jobs or 0),
                "failed_jobs": int(row.failed_jobs or 0),
                "active_jobs": int(row.active_jobs or 0),
            }
        )
    return total, items


async def get_import_batch_summary(db: AsyncSession, *, batch_id: uuid.UUID) -> dict[str, object]:
    batch = (await db.execute(select(ImportBatch).where(ImportBatch.id == batch_id))).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")

    agg_row = (
        await db.execute(
            select(
                func.count().label("total_jobs"),
                func.sum(case((ImportJob.status == "completed", 1), else_=0)).label("completed_jobs"),
                func.sum(case((ImportJob.status == "failed", 1), else_=0)).label("failed_jobs"),
                func.sum(case((ImportJob.status.in_(("queued", "processing")), 1), else_=0)).label("active_jobs"),
            ).where(ImportJob.import_batch_id == batch.id)
        )
    ).one()

    return {
        "id": str(batch.id),
        "created_by_user_id": str(batch.created_by_user_id),
        "batch_type": batch.batch_type,
        "name": batch.name,
        "created_at": batch.created_at,
        "total_jobs": int(agg_row.total_jobs or 0),
        "completed_jobs": int(agg_row.completed_jobs or 0),
        "failed_jobs": int(agg_row.failed_jobs or 0),
        "active_jobs": int(agg_row.active_jobs or 0),
    }
