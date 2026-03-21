from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any
import sys

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.models.user import User
from app.services.lexicon_jsonl_reviews import resolve_repo_local_path

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


def _import_db_module() -> Any:
    try:
        return import_module("tools.lexicon.import_db")
    except ModuleNotFoundError as exc:
        if not exc.name or not exc.name.startswith("tools"):
            raise
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        return import_module("tools.lexicon.import_db")


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
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=import_db.summarize_compiled_rows(rows),
        import_summary=None,
    )


@router.post("/run", response_model=LexiconImportResponse)
async def run_lexicon_import(
    request: LexiconImportRequest,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconImportResponse:
    input_path = _resolve_import_input_path(request.input_path, settings=settings)
    import_db = _import_db_module()
    rows = import_db.load_compiled_rows(input_path)
    return LexiconImportResponse(
        artifact_filename=input_path.name,
        input_path=str(input_path),
        row_summary=import_db.summarize_compiled_rows(rows),
        import_summary=import_db.run_import_file(
            input_path,
            source_type=request.source_type,
            source_reference=request.source_reference,
            language=request.language,
        ),
    )
