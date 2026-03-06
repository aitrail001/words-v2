import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.uploads import resolve_upload_dir
from app.models.epub_import import EpubImport
from app.models.user import User
from app.tasks.epub_processing import extract_epub_vocabulary

logger = get_logger(__name__)
router = APIRouter()

UPLOAD_DIR = resolve_upload_dir()


class ImportResponse(BaseModel):
    id: str
    user_id: str
    filename: str
    file_hash: str
    status: str
    total_words: int
    processed_words: int
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


def _to_response(epub_import: EpubImport) -> ImportResponse:
    return ImportResponse(
        id=str(epub_import.id),
        user_id=str(epub_import.user_id),
        filename=epub_import.filename,
        file_hash=epub_import.file_hash,
        status=epub_import.status,
        total_words=epub_import.total_words,
        processed_words=epub_import.processed_words,
        error_message=epub_import.error_message,
        started_at=epub_import.started_at,
        completed_at=epub_import.completed_at,
        created_at=epub_import.created_at,
    )


@router.post("", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
async def create_import(
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    """Upload an EPUB and enqueue background vocabulary extraction."""
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".epub"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .epub files are supported",
        )

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

    file_hash = hasher.hexdigest()

    existing_result = await db.execute(
        select(EpubImport)
        .where(EpubImport.user_id == current_user.id)
        .where(EpubImport.file_hash == file_hash)
        .order_by(EpubImport.created_at.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None and existing.status in {"pending", "processing"}:
        saved_path.unlink(missing_ok=True)
        response.status_code = status.HTTP_202_ACCEPTED
        return _to_response(existing)

    if existing is not None and existing.status == "completed":
        saved_path.unlink(missing_ok=True)
        response.status_code = status.HTTP_200_OK
        return _to_response(existing)

    epub_import = EpubImport(
        user_id=current_user.id,
        filename=safe_name,
        file_hash=file_hash,
    )
    db.add(epub_import)
    await db.commit()
    await db.refresh(epub_import)

    try:
        extract_epub_vocabulary.delay(
            str(epub_import.id), str(current_user.id), str(saved_path)
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue epub import task",
            import_id=str(epub_import.id),
            error=str(exc),
        )
        try:
            saved_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            logger.warning(
                "Failed to clean up uploaded file after enqueue failure",
                import_id=str(epub_import.id),
                path=str(saved_path),
                error=str(cleanup_error),
            )
        epub_import.status = "failed"
        epub_import.error_message = "Failed to queue import task"
        epub_import.completed_at = datetime.now(timezone.utc)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Import queue is unavailable",
        )

    return _to_response(epub_import)


@router.get("", response_model=list[ImportResponse])
async def list_imports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ImportResponse]:
    result = await db.execute(
        select(EpubImport)
        .where(EpubImport.user_id == current_user.id)
        .order_by(EpubImport.created_at.desc())
        .limit(50)
    )
    imports = result.scalars().all()
    return [_to_response(import_item) for import_item in imports]


@router.get("/{import_id}", response_model=ImportResponse)
async def get_import(
    import_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResponse:
    result = await db.execute(
        select(EpubImport).where(
            EpubImport.id == import_id, EpubImport.user_id == current_user.id
        )
    )
    epub_import = result.scalar_one_or_none()
    if epub_import is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import not found",
        )

    return _to_response(epub_import)
