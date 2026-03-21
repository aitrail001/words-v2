from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.models.user import User
from app.services.lexicon_jsonl_reviews import resolve_repo_local_path
from tools.lexicon.import_db import load_compiled_rows, run_import_file, summarize_compiled_rows

router = APIRouter()


class LexiconImportRequest(BaseModel):
    input_path: str
    source_type: str
    source_reference: str | None = None
    language: str = "en"


class LexiconImportResponse(BaseModel):
    artifact_filename: str
    input_path: str
    row_summary: dict[str, int]
    import_summary: dict[str, int] | None


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
    rows = load_compiled_rows(input_path)
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=summarize_compiled_rows(rows),
        import_summary=None,
    )


@router.post("/run", response_model=LexiconImportResponse)
async def run_lexicon_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    rows = load_compiled_rows(input_path)
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=summarize_compiled_rows(rows),
        import_summary=run_import_file(
            input_path,
            source_type=request.source_type,
            source_reference=request.source_reference,
            language=request.language,
        ),
    )
