from __future__ import annotations

from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any
import sys
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_job import LexiconJob
from app.models.user import User
from app.services.lexicon_compiled_reviews import default_compiled_review_output_dir
from app.services.lexicon_jobs import apply_lexicon_job_failed, create_or_reuse_lexicon_job, get_lexicon_job
from app.services.lexicon_jsonl_reviews import (
    resolve_compiled_artifact_path,
    resolve_decisions_sidecar_path,
    resolve_output_dir_path,
    resolve_repo_local_path,
)
from app.tasks.lexicon_jobs import (
    run_lexicon_compiled_materialize,
    run_lexicon_import_db,
    run_lexicon_jsonl_materialize,
)

router = APIRouter()


class LexiconJobResponse(BaseModel):
    id: str
    created_by: str | None
    job_type: str
    status: str
    target_key: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any] | None
    progress_total: int
    progress_completed: int
    progress_current_label: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class LexiconJobImportDbRequest(BaseModel):
    input_path: str
    source_type: str
    source_reference: str | None = None
    language: str = "en"


class LexiconJobJsonlMaterializeRequest(BaseModel):
    artifact_path: str
    decisions_path: str | None = None
    output_dir: str | None = None


class LexiconJobCompiledMaterializeRequest(BaseModel):
    batch_id: uuid.UUID
    output_dir: str | None = None


def _import_db_module() -> Any:
    try:
        return import_module("tools.lexicon.import_db")
    except ModuleNotFoundError as exc:
        if not exc.name or not exc.name.startswith("tools"):
            raise
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        return import_module("tools.lexicon.import_db")


def _serialize_job(job: LexiconJob) -> LexiconJobResponse:
    return LexiconJobResponse(
        id=str(job.id),
        created_by=str(job.created_by) if job.created_by else None,
        job_type=job.job_type,
        status=job.status,
        target_key=job.target_key,
        request_payload=dict(job.request_payload or {}),
        result_payload=dict(job.result_payload or {}) if job.result_payload is not None else None,
        progress_total=job.progress_total,
        progress_completed=job.progress_completed,
        progress_current_label=job.progress_current_label,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _resolve_import_input_path(raw_path: str, *, settings: Settings) -> Path:
    path = resolve_repo_local_path(raw_path, settings=settings)
    if path.is_dir():
        return path
    if path.suffix != ".jsonl":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import input must be a .jsonl file or a compiled artifact directory",
        )
    return path


async def _compiled_batch_or_404(batch_id: uuid.UUID, db: AsyncSession) -> LexiconArtifactReviewBatch:
    result = await db.execute(select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compiled review batch not found")
    return batch


async def _enqueue_or_503(db: AsyncSession, job: LexiconJob, enqueue: Any) -> None:
    try:
        enqueue.delay(str(job.id))
    except Exception:
        apply_lexicon_job_failed(job, "Failed to queue lexicon job")
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lexicon job queue is unavailable",
        ) from None


@router.post("/import-db", response_model=LexiconJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_import_db_job(
    request: LexiconJobImportDbRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LexiconJobResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    import_db = _import_db_module()
    rows = import_db.load_compiled_rows(input_path)
    row_summary = import_db.summarize_compiled_rows(rows)
    job, created = await create_or_reuse_lexicon_job(
        db,
        created_by=current_user.id,
        job_type="import_db",
        target_key=f"import_db:{input_path}",
        request_payload={
            "input_path": str(input_path),
            "source_type": request.source_type,
            "source_reference": request.source_reference,
            "language": request.language,
            "row_summary": row_summary,
        },
    )
    if created:
        await db.refresh(job)
        await db.commit()
        await _enqueue_or_503(db, job, run_lexicon_import_db)
    return _serialize_job(job)


@router.post("/jsonl-materialize", response_model=LexiconJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_jsonl_materialize_job(
    request: LexiconJobJsonlMaterializeRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LexiconJobResponse:
    artifact_path = resolve_compiled_artifact_path(request.artifact_path, settings=settings)
    decisions_path = resolve_decisions_sidecar_path(artifact_path, request.decisions_path, settings=settings)
    output_dir = resolve_output_dir_path(artifact_path, request.output_dir, settings=settings)
    job, created = await create_or_reuse_lexicon_job(
        db,
        created_by=current_user.id,
        job_type="jsonl_materialize",
        target_key=f"jsonl_materialize:{output_dir}",
        request_payload={
            "artifact_path": str(artifact_path),
            "decisions_path": str(decisions_path),
            "output_dir": str(output_dir),
        },
    )
    if created:
        await db.refresh(job)
        await db.commit()
        await _enqueue_or_503(db, job, run_lexicon_jsonl_materialize)
    return _serialize_job(job)


@router.post("/compiled-materialize", response_model=LexiconJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_compiled_materialize_job(
    request: LexiconJobCompiledMaterializeRequest,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LexiconJobResponse:
    output_dir = (
        resolve_repo_local_path(request.output_dir, settings=settings, allow_missing=True)
        if request.output_dir
        else default_compiled_review_output_dir(await _compiled_batch_or_404(request.batch_id, db), settings)
    )
    job, created = await create_or_reuse_lexicon_job(
        db,
        created_by=current_user.id,
        job_type="compiled_materialize",
        target_key=f"compiled_materialize:{request.batch_id}:{output_dir}",
        request_payload={
            "batch_id": str(request.batch_id),
            "output_dir": str(output_dir),
        },
    )
    if created:
        await db.refresh(job)
        await db.commit()
        await _enqueue_or_503(db, job, run_lexicon_compiled_materialize)
    return _serialize_job(job)


@router.get("/{job_id}", response_model=LexiconJobResponse)
async def get_lexicon_job_status(
    job_id: uuid.UUID,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> LexiconJobResponse:
    job = await get_lexicon_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lexicon job not found")
    return _serialize_job(job)
