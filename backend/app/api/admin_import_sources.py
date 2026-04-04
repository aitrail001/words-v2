import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.database import get_db
from app.models.import_source import ImportSource
from app.models.user import User
from app.services.admin_import_sources import (
    DELETE_MODE_CACHE_ONLY,
    get_admin_import_source_detail,
    list_admin_import_sources,
    list_import_source_jobs,
    soft_delete_import_source_cache,
)
from app.services.source_imports import fetch_review_entries

router = APIRouter()


class AdminImportSourceListResponse(BaseModel):
    total: int
    items: list[dict]


class AdminImportSourceBulkDeleteRequest(BaseModel):
    source_ids: list[uuid.UUID]
    delete_mode: str = DELETE_MODE_CACHE_ONLY
    deletion_reason: str | None = None


@router.get("", response_model=AdminImportSourceListResponse)
async def list_sources(
    q: str | None = Query(default=None),
    status: str | None = Query(default="all"),
    sort: str = Query(default="processed_at"),
    order: str = Query(default="desc"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminImportSourceListResponse:
    total, items = await list_admin_import_sources(
        db,
        q=q,
        status_filter=status,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return AdminImportSourceListResponse(total=total, items=items)


@router.get("/{source_id}")
async def get_source_detail(
    source_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    source_summary = await get_admin_import_source_detail(db, source_id=source_id)
    if source_summary is None:
        raise HTTPException(status_code=404, detail="Import source not found")
    return source_summary


@router.get("/{source_id}/jobs")
async def get_source_jobs(
    source_id: uuid.UUID,
    from_cache: str = Query(default="all"),
    job_origin: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    total, items = await list_import_source_jobs(
        db,
        source_id=source_id,
        from_cache=from_cache,
        job_origin=job_origin,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": items}


@router.get("/{source_id}/entries")
async def get_source_entries(
    source_id: uuid.UUID,
    q: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    phrase_kind: str | None = Query(default=None),
    sort: str = Query(default="book_frequency"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    source = (await db.execute(select(ImportSource).where(ImportSource.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Import source not found")
    if source.deleted_at is not None:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "IMPORT_CACHE_DELETED",
                "message": "This cached import is no longer available. Re-upload the EPUB to regenerate import cache.",
            },
        )
    total, items = await fetch_review_entries(
        db,
        import_source_id=source_id,
        q=q,
        entry_type=entry_type,
        phrase_kind=phrase_kind,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "items": items}


@router.delete("/{source_id}")
async def delete_source_cache(
    source_id: uuid.UUID,
    delete_mode: str = Query(default=DELETE_MODE_CACHE_ONLY),
    deletion_reason: str | None = Query(default=None),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    source = (await db.execute(select(ImportSource).where(ImportSource.id == source_id))).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Import source not found")
    result = await soft_delete_import_source_cache(
        db,
        source=source,
        deleted_by=current_user,
        delete_mode=delete_mode,
        deletion_reason=deletion_reason,
    )
    return {
        "source_id": str(result.source_id),
        "deleted_entry_count": result.deleted_entry_count,
        "deleted_orphan_job_count": result.deleted_orphan_job_count,
        "delete_mode": delete_mode,
    }


@router.post("/bulk-delete")
async def bulk_delete_sources(
    request: AdminImportSourceBulkDeleteRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not request.source_ids:
        return {"deleted": []}

    deleted: list[dict[str, object]] = []
    for source_id in request.source_ids:
        source = (await db.execute(select(ImportSource).where(ImportSource.id == source_id))).scalar_one_or_none()
        if source is None:
            continue
        result = await soft_delete_import_source_cache(
            db,
            source=source,
            deleted_by=current_user,
            delete_mode=request.delete_mode,
            deletion_reason=request.deletion_reason,
        )
        deleted.append(
            {
                "source_id": str(result.source_id),
                "deleted_entry_count": result.deleted_entry_count,
                "deleted_orphan_job_count": result.deleted_orphan_job_count,
            }
        )

    return {
        "delete_mode": request.delete_mode,
        "deleted": deleted,
    }
