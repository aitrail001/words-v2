from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.models.user import User
from app.services.lexicon_import_jobs import (
    create_lexicon_import_job,
    get_lexicon_import_job,
    serialize_lexicon_import_job,
)
from app.services.lexicon_jsonl_reviews import resolve_repo_local_path
from app.services.lexicon_tool_imports import import_lexicon_tool_module

router = APIRouter()


class LexiconImportRequest(BaseModel):
    input_path: str
    source_type: str
    source_reference: str | None = None
    language: str = "en"
    conflict_mode: str = "upsert"
    error_mode: str = "fail_fast"


class LexiconImportResponse(BaseModel):
    artifact_filename: str
    input_path: str
    row_summary: dict[str, int]
    import_summary: dict[str, int] | None
    error_samples: list[dict[str, str]] | None = None


class LexiconImportJobResponse(BaseModel):
    id: str
    artifact_filename: str
    input_path: str
    source_type: str
    source_reference: str | None
    language: str
    conflict_mode: str
    error_mode: str
    status: str
    row_summary: dict[str, int]
    import_summary: dict[str, int] | None
    total_rows: int
    completed_rows: int
    remaining_rows: int
    current_entry: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


def _import_db_module():
    return import_lexicon_tool_module("tools.lexicon.import_db")


def _voice_import_db_module():
    return import_lexicon_tool_module("tools.lexicon.voice_import_db")


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


@router.post("/dry-run", response_model=LexiconImportResponse)
async def dry_run_lexicon_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    import_db = _import_db_module()
    rows = import_db.load_compiled_rows(input_path)
    error_samples: list[dict[str, str]] = []
    import_summary = import_db.run_import_file(
        input_path,
        source_type=request.source_type,
        source_reference=request.source_reference,
        language=request.language,
        rows=rows,
        conflict_mode=request.conflict_mode,
        error_mode=request.error_mode,
        dry_run=True,
        error_samples_sink=error_samples,
    )
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=import_db.summarize_compiled_rows(rows),
        import_summary={
            key: int(value)
            for key, value in import_summary.items()
            if isinstance(value, bool) or isinstance(value, int)
        },
        error_samples=(
            [
                {"entry": str(item.get("entry", "")), "error": str(item.get("error", ""))}
                for item in error_samples
                if isinstance(item, dict)
            ]
            or None
        ),
    )


@router.post("/run", response_model=LexiconImportJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_lexicon_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportJobResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    import_db = _import_db_module()
    rows = import_db.load_compiled_rows(input_path)
    job = create_lexicon_import_job(
        input_path=input_path,
        source_type=request.source_type,
        source_reference=request.source_reference,
        language=request.language,
        conflict_mode=request.conflict_mode,
        error_mode=request.error_mode,
        rows=rows,
        import_runner=import_db.run_import_file,
        row_summary=import_db.summarize_compiled_rows(rows),
    )
    return LexiconImportJobResponse(**serialize_lexicon_import_job(job))


@router.get("/jobs/{job_id}", response_model=LexiconImportJobResponse)
async def get_lexicon_import_job_status(
    job_id: str,
    _: User = Depends(get_current_admin_user),
) -> LexiconImportJobResponse:
    job = get_lexicon_import_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lexicon import job not found",
    )
    return LexiconImportJobResponse(**serialize_lexicon_import_job(job))


@router.post("/voice-dry-run", response_model=LexiconImportResponse)
async def dry_run_lexicon_voice_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    voice_import_db = _voice_import_db_module()
    rows = voice_import_db.load_voice_manifest_rows(input_path)
    import_summary = voice_import_db.run_voice_import_file(
        input_path,
        language=request.language,
        conflict_mode=request.conflict_mode,
        error_mode=request.error_mode,
        dry_run=True,
        rows=rows,
    )
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=voice_import_db.summarize_voice_manifest_rows(rows),
        import_summary={
            key: int(value)
            for key, value in import_summary.items()
            if isinstance(value, bool) or isinstance(value, int)
        },
    )


@router.post("/voice-run", response_model=LexiconImportJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_lexicon_voice_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportJobResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    voice_import_db = _voice_import_db_module()
    rows = voice_import_db.load_voice_manifest_rows(input_path)
    job = create_lexicon_import_job(
        input_path=input_path,
        source_type=request.source_type,
        source_reference=request.source_reference,
        language=request.language,
        conflict_mode=request.conflict_mode,
        error_mode=request.error_mode,
        rows=rows,
        import_runner=voice_import_db.run_voice_import_file,
        row_summary=voice_import_db.summarize_voice_manifest_rows(rows),
    )
    return LexiconImportJobResponse(**serialize_lexicon_import_job(job))
