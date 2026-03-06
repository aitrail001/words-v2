import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.import_job import ImportJob
from app.models.user import User
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem
from app.tasks.epub_processing import process_word_list_import

logger = get_logger(__name__)
router = APIRouter()

UPLOAD_DIR = Path("/tmp/words_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ImportJobResponse(BaseModel):
    id: str
    user_id: str
    book_id: str | None
    word_list_id: str | None
    status: str
    source_filename: str
    source_hash: str
    list_name: str
    list_description: str | None
    total_items: int
    processed_items: int
    created_count: int
    skipped_count: int
    not_found_count: int
    not_found_words: list[str] | None
    error_count: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class WordListItemResponse(BaseModel):
    id: str
    word_id: str
    context_sentence: str | None
    frequency_count: int
    variation_data: dict | None
    added_at: datetime


class WordListResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    source_type: str | None
    source_reference: str | None
    book_id: str | None
    created_at: datetime


class WordListDetailResponse(WordListResponse):
    items: list[WordListItemResponse]


class AddWordListItemRequest(BaseModel):
    word_id: uuid.UUID
    context_sentence: str | None = None
    frequency_count: int = Field(default=1, ge=1)
    variation_data: dict | None = None


TERMINAL_STATUSES = {"completed", "failed"}


def _to_import_job_response(job: ImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        id=str(job.id),
        user_id=str(job.user_id),
        book_id=str(job.book_id) if job.book_id else None,
        word_list_id=str(job.word_list_id) if job.word_list_id else None,
        status=job.status,
        source_filename=job.source_filename,
        source_hash=job.source_hash,
        list_name=job.list_name,
        list_description=job.list_description,
        total_items=job.total_items,
        processed_items=job.processed_items,
        created_count=job.created_count,
        skipped_count=job.skipped_count,
        not_found_count=job.not_found_count,
        not_found_words=job.not_found_words,
        error_count=job.error_count,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _to_word_list_response(word_list: WordList) -> WordListResponse:
    return WordListResponse(
        id=str(word_list.id),
        user_id=str(word_list.user_id),
        name=word_list.name,
        description=word_list.description,
        source_type=word_list.source_type,
        source_reference=word_list.source_reference,
        book_id=str(word_list.book_id) if word_list.book_id else None,
        created_at=word_list.created_at,
    )


def _to_word_list_item_response(item: WordListItem) -> WordListItemResponse:
    return WordListItemResponse(
        id=str(item.id),
        word_id=str(item.word_id),
        context_sentence=item.context_sentence,
        frequency_count=item.frequency_count,
        variation_data=item.variation_data,
        added_at=item.added_at,
    )


@router.post("/import", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_word_list_import(
    response: Response,
    file: UploadFile = File(...),
    list_name: str | None = Form(default=None),
    list_description: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
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

    source_hash = hasher.hexdigest()

    existing_result = await db.execute(
        select(ImportJob)
        .where(ImportJob.user_id == current_user.id)
        .where(ImportJob.source_hash == source_hash)
        .order_by(ImportJob.created_at.desc())
        .limit(1)
    )
    existing = existing_result.scalar_one_or_none()

    if existing is not None and existing.status not in TERMINAL_STATUSES:
        saved_path.unlink(missing_ok=True)
        response.status_code = status.HTTP_202_ACCEPTED
        return _to_import_job_response(existing)

    if existing is not None and existing.status == "completed":
        saved_path.unlink(missing_ok=True)
        response.status_code = status.HTTP_200_OK
        return _to_import_job_response(existing)

    job = ImportJob(
        user_id=current_user.id,
        source_filename=safe_name,
        source_hash=source_hash,
        list_name=(list_name or Path(safe_name).stem).strip() or "Imported words",
        list_description=list_description,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    try:
        process_word_list_import.delay(str(job.id), str(current_user.id), str(saved_path))
    except Exception as exc:
        logger.error(
            "Failed to enqueue word list import task",
            import_job_id=str(job.id),
            error=str(exc),
        )
        saved_path.unlink(missing_ok=True)
        job.status = "failed"
        job.error_count += 1
        job.error_message = "Failed to queue import task"
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Import queue is unavailable",
        )

    return _to_import_job_response(job)


@router.get("", response_model=list[WordListResponse])
async def list_word_lists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WordListResponse]:
    result = await db.execute(
        select(WordList)
        .where(WordList.user_id == current_user.id)
        .order_by(WordList.created_at.desc())
        .limit(100)
    )
    word_lists = result.scalars().all()
    return [_to_word_list_response(word_list) for word_list in word_lists]


@router.get("/{word_list_id}", response_model=WordListDetailResponse)
async def get_word_list(
    word_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    result = await db.execute(
        select(WordList).where(
            WordList.id == word_list_id,
            WordList.user_id == current_user.id,
        )
    )
    word_list = result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")

    items_result = await db.execute(
        select(WordListItem)
        .where(WordListItem.word_list_id == word_list.id)
        .order_by(WordListItem.added_at.desc())
    )
    items = items_result.scalars().all()

    base = _to_word_list_response(word_list)
    return WordListDetailResponse(
        **base.model_dump(),
        items=[_to_word_list_item_response(item) for item in items],
    )


@router.post("/{word_list_id}/items", response_model=WordListItemResponse, status_code=status.HTTP_201_CREATED)
async def add_word_list_item(
    word_list_id: uuid.UUID,
    request: AddWordListItemRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListItemResponse:
    list_result = await db.execute(
        select(WordList).where(
            WordList.id == word_list_id,
            WordList.user_id == current_user.id,
        )
    )
    word_list = list_result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")

    existing_result = await db.execute(
        select(WordListItem).where(
            WordListItem.word_list_id == word_list_id,
            WordListItem.word_id == request.word_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        existing.frequency_count += request.frequency_count
        if request.context_sentence:
            existing.context_sentence = request.context_sentence
        if request.variation_data:
            existing.variation_data = request.variation_data
        await db.commit()
        await db.refresh(existing)
        response.status_code = status.HTTP_200_OK
        return _to_word_list_item_response(existing)

    item = WordListItem(
        word_list_id=word_list_id,
        word_id=request.word_id,
        context_sentence=request.context_sentence,
        frequency_count=request.frequency_count,
        variation_data=request.variation_data,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return _to_word_list_item_response(item)


@router.delete("/{word_list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word_list_item(
    word_list_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    list_result = await db.execute(
        select(WordList).where(
            WordList.id == word_list_id,
            WordList.user_id == current_user.id,
        )
    )
    word_list = list_result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")

    item_result = await db.execute(
        select(WordListItem).where(
            WordListItem.id == item_id,
            WordListItem.word_list_id == word_list_id,
        )
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Word list item not found",
        )

    await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{word_list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word_list(
    word_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(WordList).where(
            WordList.id == word_list_id,
            WordList.user_id == current_user.id,
        )
    )
    word_list = result.scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Word list not found")

    await db.delete(word_list)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
