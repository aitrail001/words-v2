import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.uploads import resolve_upload_dir
from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.learner_catalog_entry import LearnerCatalogEntry
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.translation import Translation
from app.models.user import User
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem
from app.services.knowledge_map import (
    build_word_translation_map,
    get_preferences,
    load_phrase_summary_map,
    load_word_primary_definitions,
)
from app.services.source_imports import (
    ENTRY_TYPE_PHRASE,
    ENTRY_TYPE_WORD,
    SOURCE_TYPE_EPUB,
    create_import_job,
    fetch_import_matcher,
    get_or_create_import_source,
    hydrate_word_list_items,
    parse_bulk_entry_text,
)
from app.tasks.epub_processing import process_word_list_import

logger = get_logger(__name__)
router = APIRouter()
UPLOAD_DIR = resolve_upload_dir()
MAX_ACTIVE_IMPORTS_PER_USER = 3


class ImportJobResponse(BaseModel):
    id: str
    user_id: str
    import_source_id: str | None
    word_list_id: str | None
    status: str
    source_filename: str
    source_hash: str
    list_name: str
    list_description: str | None
    total_items: int
    processed_items: int
    progress_stage: str | None
    progress_total: int
    progress_completed: int
    progress_current_label: str | None
    matched_entry_count: int
    created_count: int
    skipped_count: int
    not_found_count: int
    not_found_words: list[str] | None
    error_count: int
    error_message: str | None
    source_title: str | None
    source_author: str | None
    source_publisher: str | None
    source_language: str | None
    source_identifier: str | None
    source_published_year: int | None
    source_isbn: str | None
    from_cache: bool
    processing_duration_seconds: float | None
    total_entries_extracted: int
    word_entry_count: int
    phrase_entry_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class WordListItemResponse(BaseModel):
    id: str
    entry_type: str
    entry_id: str
    display_text: str | None
    normalized_form: str | None
    browse_rank: int | None
    cefr_level: str | None
    phrase_kind: str | None
    part_of_speech: str | None
    translation: str | None = None
    primary_definition: str | None = None
    status: str
    frequency_count: int
    added_at: datetime


class WordListResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    source_type: str | None
    source_reference: str | None
    created_at: datetime


class WordListDetailResponse(WordListResponse):
    items: list[WordListItemResponse]


class CreateWordListRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class UpdateWordListRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class EntryReferenceRequest(BaseModel):
    entry_type: str
    entry_id: uuid.UUID


class AddWordListItemRequest(EntryReferenceRequest):
    frequency_count: int = Field(default=1, ge=1)


class ReviewEntriesResponse(BaseModel):
    total: int
    items: list[dict]


class CreateWordListFromImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    selected_entries: list[EntryReferenceRequest]


class BulkResolveRequest(BaseModel):
    raw_text: str


class BulkResolveResponse(BaseModel):
    found_entries: list[dict]
    ambiguous_entries: list[str]
    not_found_count: int


class BulkAddRequest(BaseModel):
    selected_entries: list[EntryReferenceRequest]


class BulkDeleteWordListsRequest(BaseModel):
    word_list_ids: list[uuid.UUID]


class BulkDeleteWordListItemsRequest(BaseModel):
    item_ids: list[uuid.UUID]


def _to_import_job_response(job: ImportJob) -> ImportJobResponse:
    import_source = getattr(job, "import_source", None)
    from_cache = bool(job.status == "completed" and job.started_at is None and import_source is not None)
    processing_duration_seconds = None
    if job.started_at is not None and job.completed_at is not None:
        processing_duration_seconds = max(
            0.0,
            (job.completed_at - job.started_at).total_seconds(),
        )
    total_entries_extracted = job.matched_entry_count
    word_entry_count = getattr(job, "word_entry_count", 0) or 0
    phrase_entry_count = getattr(job, "phrase_entry_count", 0) or 0
    if import_source is not None:
        total_entries_extracted = import_source.matched_entry_count
    return ImportJobResponse(
        id=str(job.id),
        user_id=str(job.user_id),
        import_source_id=str(job.import_source_id) if job.import_source_id else None,
        word_list_id=str(job.word_list_id) if job.word_list_id else None,
        status=job.status,
        source_filename=job.source_filename,
        source_hash=job.source_hash,
        list_name=job.list_name,
        list_description=job.list_description,
        total_items=job.total_items,
        processed_items=job.processed_items,
        progress_stage=job.progress_stage,
        progress_total=job.progress_total,
        progress_completed=job.progress_completed,
        progress_current_label=job.progress_current_label,
        matched_entry_count=job.matched_entry_count,
        created_count=job.created_count,
        skipped_count=job.skipped_count,
        not_found_count=job.not_found_count,
        not_found_words=job.not_found_words,
        error_count=job.error_count,
        error_message=job.error_message,
        source_title=import_source.title if import_source else None,
        source_author=import_source.author if import_source else None,
        source_publisher=import_source.publisher if import_source else None,
        source_language=import_source.language if import_source else None,
        source_identifier=import_source.source_identifier if import_source else None,
        source_published_year=import_source.published_year if import_source else None,
        source_isbn=import_source.isbn if import_source else None,
        from_cache=from_cache,
        processing_duration_seconds=processing_duration_seconds,
        total_entries_extracted=total_entries_extracted,
        word_entry_count=word_entry_count,
        phrase_entry_count=phrase_entry_count,
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
        created_at=word_list.created_at,
    )


def _validate_entry_type(entry_type: str) -> str:
    if entry_type not in {ENTRY_TYPE_WORD, ENTRY_TYPE_PHRASE}:
        raise HTTPException(status_code=400, detail="Unsupported entry type")
    return entry_type


async def _get_word_list_for_user(
    db: AsyncSession,
    *,
    word_list_id: uuid.UUID,
    user_id: uuid.UUID,
) -> WordList:
    word_list = (
        await db.execute(
            select(WordList).where(WordList.id == word_list_id, WordList.user_id == user_id)
        )
    ).scalar_one_or_none()
    if word_list is None:
        raise HTTPException(status_code=404, detail="Word list not found")
    return word_list


async def _get_import_job_for_user(
    db: AsyncSession,
    *,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ImportJob:
    job = (
        await db.execute(
            select(ImportJob).where(ImportJob.id == job_id, ImportJob.user_id == user_id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


async def _hydrate_import_jobs_with_source_details(
    db: AsyncSession,
    jobs: list[ImportJob],
) -> list[ImportJob]:
    import_source_ids = [job.import_source_id for job in jobs if job.import_source_id is not None]
    if not import_source_ids:
        return jobs

    import_sources = (
        await db.execute(select(ImportSource).where(ImportSource.id.in_(import_source_ids)))
    ).scalars().all()
    sources_by_id = {source.id: source for source in import_sources}

    counts_result = await db.execute(
        select(
            ImportSourceEntry.import_source_id,
            func.count().label("total_entries"),
            func.sum(case((ImportSourceEntry.entry_type == ENTRY_TYPE_WORD, 1), else_=0)).label("word_entries"),
            func.sum(case((ImportSourceEntry.entry_type == ENTRY_TYPE_PHRASE, 1), else_=0)).label("phrase_entries"),
        )
        .where(ImportSourceEntry.import_source_id.in_(import_source_ids))
        .group_by(ImportSourceEntry.import_source_id)
    )
    counts_by_source_id = {
        row.import_source_id: row
        for row in counts_result.all()
    }

    for job in jobs:
        if job.import_source_id is None:
            continue
        setattr(job, "import_source", sources_by_id.get(job.import_source_id))
        count_row = counts_by_source_id.get(job.import_source_id)
        setattr(job, "word_entry_count", int(getattr(count_row, "word_entries", 0) or 0))
        setattr(job, "phrase_entry_count", int(getattr(count_row, "phrase_entries", 0) or 0))
    return jobs


async def _hydrate_word_list_summary_fields(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    items: list[dict[str, object]],
) -> list[dict[str, object]]:
    word_ids = [
        uuid.UUID(str(item["entry_id"]))
        for item in items
        if item["entry_type"] == ENTRY_TYPE_WORD
    ]
    phrase_ids = [
        uuid.UUID(str(item["entry_id"]))
        for item in items
        if item["entry_type"] == ENTRY_TYPE_PHRASE
    ]
    if not word_ids and not phrase_ids:
        return items

    preferences = await get_preferences(db, user_id)

    if word_ids:
        primary_meanings = await load_word_primary_definitions(db, word_ids)
        meaning_ids = [meaning.id for meaning in primary_meanings.values()]
        translations: list[Translation] = []
        if meaning_ids:
            translations_result = await db.execute(
                select(Translation)
                .where(Translation.meaning_id.in_(meaning_ids))
                .order_by(Translation.meaning_id.asc(), Translation.language.asc())
            )
            translations = translations_result.scalars().all()
        translation_map = build_word_translation_map(translations, preferences.translation_locale)
        for item in items:
            if item["entry_type"] != ENTRY_TYPE_WORD:
                continue
            meaning = primary_meanings.get(uuid.UUID(str(item["entry_id"])))
            if meaning is None:
                continue
            item["primary_definition"] = meaning.definition
            item["translation"] = translation_map.get(meaning.id)

    if phrase_ids:
        phrase_summary_map = await load_phrase_summary_map(db, phrase_ids, preferences.translation_locale)
        for item in items:
            if item["entry_type"] != ENTRY_TYPE_PHRASE:
                continue
            summary_row = phrase_summary_map.get(uuid.UUID(str(item["entry_id"])))
            if summary_row is None:
                continue
            item["primary_definition"] = summary_row.get("primary_definition")
            item["translation"] = summary_row.get("translation")

    return items


async def _get_duplicate_word_list_name(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    exclude_word_list_id: uuid.UUID | None = None,
) -> WordList | None:
    normalized_name = name.strip().lower()
    conditions = [
        WordList.user_id == user_id,
        func.lower(WordList.name) == normalized_name,
    ]
    if exclude_word_list_id is not None:
        conditions.append(WordList.id != exclude_word_list_id)
    return (
        await db.execute(select(WordList).where(and_(*conditions)))
    ).scalar_one_or_none()


async def _assert_unique_word_list_name(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    exclude_word_list_id: uuid.UUID | None = None,
) -> None:
    duplicate = await _get_duplicate_word_list_name(
        db,
        user_id=user_id,
        name=name,
        exclude_word_list_id=exclude_word_list_id,
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Word list name already exists")


async def _create_import_job_from_upload(
    *,
    db: AsyncSession,
    user: User,
    file: UploadFile,
    list_name: str | None,
    list_description: str | None,
    response: Response,
) -> ImportJobResponse:
    user_id = user.id
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".epub"):
        raise HTTPException(status_code=400, detail="Only .epub files are supported")

    active_import_count = int(
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
    if active_import_count >= MAX_ACTIVE_IMPORTS_PER_USER:
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
    )

    if import_source.status == "completed":
        response.status_code = status.HTTP_200_OK
        saved_path.unlink(missing_ok=True)
        return _to_import_job_response(job)

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

    response.status_code = status.HTTP_201_CREATED
    return _to_import_job_response(job)


@router.post("/import", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED)
async def create_word_list_import(
    response: Response,
    file: UploadFile = File(...),
    list_name: str | None = Form(default=None),
    list_description: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    return await _create_import_job_from_upload(
        db=db,
        user=current_user,
        file=file,
        list_name=list_name,
        list_description=list_description,
        response=response,
    )


@router.post("", response_model=WordListResponse, status_code=status.HTTP_201_CREATED)
async def create_empty_word_list(
    request: CreateWordListRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListResponse:
    normalized_name = request.name.strip()
    await _assert_unique_word_list_name(db, user_id=current_user.id, name=normalized_name)
    word_list = WordList(
        user_id=current_user.id,
        name=normalized_name,
        description=request.description,
    )
    db.add(word_list)
    await db.commit()
    await db.refresh(word_list)
    return _to_word_list_response(word_list)


@router.get("", response_model=list[WordListResponse])
async def list_word_lists(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WordListResponse]:
    rows = (
        await db.execute(
            select(WordList)
            .where(WordList.user_id == current_user.id)
            .order_by(WordList.created_at.desc())
        )
    ).scalars().all()
    return [_to_word_list_response(row) for row in rows]


@router.get("/{word_list_id}", response_model=WordListDetailResponse)
async def get_word_list(
    word_list_id: uuid.UUID,
    q: str | None = Query(default=None),
    sort: str = Query(default="alpha"),
    order: str = Query(default="asc"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    word_list = await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    item_rows = (
        await db.execute(
            select(WordListItem).where(WordListItem.word_list_id == word_list.id)
        )
    ).scalars().all()
    learner_catalog: dict[tuple[str, uuid.UUID], dict[str, object]] = {}
    learner_statuses: dict[tuple[str, uuid.UUID], str] = {}
    if item_rows:
        catalog_rows = (
            await db.execute(
                select(LearnerCatalogEntry).where(
                    or_(
                        *[
                            and_(
                                LearnerCatalogEntry.entry_type == item.entry_type,
                                LearnerCatalogEntry.entry_id == item.entry_id,
                            )
                            for item in item_rows
                        ]
                    )
                )
            )
        ).scalars().all()
        learner_catalog = {
            (row.entry_type, row.entry_id): {
                "display_text": row.display_text,
                "normalized_form": row.normalized_form,
                "browse_rank": row.browse_rank,
                "cefr_level": row.cefr_level,
                "phrase_kind": row.phrase_kind,
                "primary_part_of_speech": row.primary_part_of_speech,
            }
            for row in catalog_rows
        }
        status_rows = (
            await db.execute(
                select(LearnerEntryStatus).where(
                    LearnerEntryStatus.user_id == current_user.id,
                    or_(
                        *[
                            and_(
                                LearnerEntryStatus.entry_type == item.entry_type,
                                LearnerEntryStatus.entry_id == item.entry_id,
                            )
                            for item in item_rows
                        ]
                    ),
                )
            )
        ).scalars().all()
        learner_statuses = {
            (row.entry_type, row.entry_id): row.status
            for row in status_rows
        }
    items = hydrate_word_list_items(item_rows, learner_catalog)
    items = await _hydrate_word_list_summary_fields(
        db,
        user_id=current_user.id,
        items=items,
    )
    for item in items:
        item["status"] = learner_statuses.get(
            (item["entry_type"], uuid.UUID(item["entry_id"])),
            "undecided",
        )
    if q:
        lowered = q.strip().lower()
        items = [
            item for item in items
            if lowered in str(item.get("display_text") or "").lower()
            or lowered in str(item.get("normalized_form") or "").lower()
        ]
    normalized_order = "desc" if order == "desc" else "asc"
    normalized_sort = sort if sort in {"alpha", "rank"} else "alpha"
    if normalized_sort == "rank":
        if normalized_order == "desc":
            items.sort(
                key=lambda item: (
                    item.get("browse_rank") is None,
                    -(item.get("browse_rank") or 0),
                    str(item.get("display_text") or "").lower(),
                ),
            )
        else:
            items.sort(
                key=lambda item: (
                    item.get("browse_rank") is None,
                    item.get("browse_rank") or 1_000_000,
                    str(item.get("display_text") or "").lower(),
                ),
            )
    else:
        items.sort(
            key=lambda item: (
                str(item.get("display_text") or "").lower(),
                item.get("browse_rank") or 1_000_000,
            ),
        )
        if normalized_order == "desc":
            items.reverse()

    return WordListDetailResponse(
        **_to_word_list_response(word_list).model_dump(),
        items=[WordListItemResponse(**item) for item in items],
    )


@router.patch("/{word_list_id}", response_model=WordListResponse)
async def update_word_list(
    word_list_id: uuid.UUID,
    request: UpdateWordListRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListResponse:
    word_list = await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    if request.name is not None:
        normalized_name = request.name.strip()
        await _assert_unique_word_list_name(
            db,
            user_id=current_user.id,
            name=normalized_name,
            exclude_word_list_id=word_list.id,
        )
        word_list.name = normalized_name
    if "description" in request.model_fields_set:
        word_list.description = request.description
    await db.commit()
    await db.refresh(word_list)
    return _to_word_list_response(word_list)


@router.delete("/{word_list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word_list(
    word_list_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    word_list = await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    await db.delete(word_list)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_word_lists(
    request: BulkDeleteWordListsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if not request.word_list_ids:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    word_lists = (
        await db.execute(
            select(WordList).where(
                WordList.user_id == current_user.id,
                WordList.id.in_(request.word_list_ids),
            )
        )
    ).scalars().all()
    for word_list in word_lists:
        await db.delete(word_list)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{word_list_id}/items", response_model=WordListItemResponse, status_code=status.HTTP_201_CREATED)
async def add_word_list_item(
    word_list_id: uuid.UUID,
    request: AddWordListItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListItemResponse:
    word_list = await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    entry_type = _validate_entry_type(request.entry_type)
    catalog_row = (
        await db.execute(
            select(LearnerCatalogEntry).where(
                LearnerCatalogEntry.entry_type == entry_type,
                LearnerCatalogEntry.entry_id == request.entry_id,
            )
        )
    ).scalar_one_or_none()
    if catalog_row is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    existing_item = (
        await db.execute(
            select(WordListItem).where(
                WordListItem.word_list_id == word_list.id,
                WordListItem.entry_type == entry_type,
                WordListItem.entry_id == request.entry_id,
            )
        )
    ).scalar_one_or_none()
    if existing_item is not None:
        existing_item.frequency_count += request.frequency_count
        await db.commit()
        await db.refresh(existing_item)
        return WordListItemResponse(
            id=str(existing_item.id),
            entry_type=existing_item.entry_type,
            entry_id=str(existing_item.entry_id),
            display_text=catalog_row.display_text,
            normalized_form=catalog_row.normalized_form,
            browse_rank=catalog_row.browse_rank,
            cefr_level=catalog_row.cefr_level,
            phrase_kind=catalog_row.phrase_kind,
            part_of_speech=catalog_row.primary_part_of_speech,
            translation=None,
            primary_definition=None,
            status="undecided",
            frequency_count=existing_item.frequency_count,
            added_at=existing_item.added_at,
        )

    item = WordListItem(
        word_list_id=word_list.id,
        entry_type=entry_type,
        entry_id=request.entry_id,
        frequency_count=request.frequency_count,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return WordListItemResponse(
        id=str(item.id),
        entry_type=item.entry_type,
        entry_id=str(item.entry_id),
        display_text=catalog_row.display_text,
        normalized_form=catalog_row.normalized_form,
        browse_rank=catalog_row.browse_rank,
        cefr_level=catalog_row.cefr_level,
        phrase_kind=catalog_row.phrase_kind,
        part_of_speech=catalog_row.primary_part_of_speech,
        translation=None,
        primary_definition=None,
        status="undecided",
        frequency_count=item.frequency_count,
        added_at=item.added_at,
    )


@router.delete("/{word_list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_word_list_item(
    word_list_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    item = (
        await db.execute(
            select(WordListItem).where(
                WordListItem.id == item_id,
                WordListItem.word_list_id == word_list_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Word list item not found")
    await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{word_list_id}/items", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_word_list_items(
    word_list_id: uuid.UUID,
    request: BulkDeleteWordListItemsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _get_word_list_for_user(db, word_list_id=word_list_id, user_id=current_user.id)
    if not request.item_ids:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    items = (
        await db.execute(
            select(WordListItem).where(
                WordListItem.word_list_id == word_list_id,
                WordListItem.id.in_(request.item_ids),
            )
        )
    ).scalars().all()
    for item in items:
        await db.delete(item)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/resolve-entries", response_model=BulkResolveResponse)
async def resolve_entries(
    request: BulkResolveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkResolveResponse:
    del current_user
    terms = parse_bulk_entry_text(request.raw_text)
    matcher, phrase_catalog, learner_catalog = await fetch_import_matcher(db)
    resolved = matcher.resolve_terms(
        terms,
        phrase_catalog=phrase_catalog,
        learner_catalog=learner_catalog,
    )
    return BulkResolveResponse(**resolved)


@router.post("/{word_list_id}/bulk-add", response_model=WordListDetailResponse)
async def bulk_add_entries(
    word_list_id: uuid.UUID,
    request: BulkAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListDetailResponse:
    for entry in request.selected_entries:
        await add_word_list_item(
            word_list_id=word_list_id,
            request=AddWordListItemRequest(
                entry_type=entry.entry_type,
                entry_id=entry.entry_id,
                frequency_count=1,
            ),
            current_user=current_user,
            db=db,
        )
    return await get_word_list(
        word_list_id=word_list_id,
        q=None,
        sort="alpha",
        order="asc",
        current_user=current_user,
        db=db,
    )


@router.get("/imports/{job_id}/entries", response_model=ReviewEntriesResponse)
async def legacy_import_entries(
    job_id: uuid.UUID,
    q: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    phrase_kind: str | None = Query(default=None),
    sort: str = Query(default="book_frequency"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewEntriesResponse:
    from app.api.import_jobs import list_import_job_entries

    return await list_import_job_entries(
        job_id=job_id,
        q=q,
        entry_type=entry_type,
        phrase_kind=phrase_kind,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
        current_user=current_user,
        db=db,
    )


@router.post("/imports/{job_id}/word-lists", response_model=WordListResponse, status_code=status.HTTP_201_CREATED)
async def legacy_create_list_from_import(
    job_id: uuid.UUID,
    request: CreateWordListFromImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WordListResponse:
    from app.api.import_jobs import create_word_list_from_import_job

    return await create_word_list_from_import_job(
        job_id=job_id,
        request=request,
        current_user=current_user,
        db=db,
    )
