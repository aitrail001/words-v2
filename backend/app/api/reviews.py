import uuid
from datetime import datetime
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_admin_user, get_current_user
from app.api.request_db_metrics import finalize_request_db_metrics
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import User
from app.services.review import ReviewService

logger = get_logger(__name__)
router = APIRouter()


class QueueAddRequest(BaseModel):
    meaning_id: uuid.UUID


class QueueSubmitRequest(BaseModel):
    quality: int = Field(..., ge=0, le=5)
    confirm: bool = False
    time_spent_ms: int = Field(..., ge=0)
    audio_replay_count: int = Field(default=0, ge=0)
    card_type: str | None = Field(default=None, min_length=1, max_length=32)
    prompt_token: str | None = Field(default=None, min_length=1, max_length=4096)
    review_mode: str | None = None
    outcome: str | None = Field(default=None, max_length=32)
    selected_option_id: str | None = Field(default=None, min_length=1, max_length=1)
    typed_answer: str | None = Field(default=None, max_length=256)
    prompt: dict[str, Any] | None = Field(default=None)
    schedule_override: str | None = Field(default=None, max_length=32)

    @field_validator("schedule_override")
    @classmethod
    def validate_schedule_override(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in ReviewService.SCHEDULE_OVERRIDE_VALUES:
            raise ValueError("Invalid schedule_override")
        return value


class ReviewOption(BaseModel):
    option_id: str
    label: str


class ReviewPromptAudioVariant(BaseModel):
    playback_url: str
    locale: str
    relative_path: str | None = None


class ReviewPromptAudioPayload(BaseModel):
    preferred_playback_url: str | None = None
    preferred_locale: str | None = None
    locales: dict[str, ReviewPromptAudioVariant] = Field(default_factory=dict)


class ReviewPrompt(BaseModel):
    mode: str
    prompt_type: str
    prompt_token: str | None = None
    stem: str | None = None
    question: str
    options: list[ReviewOption] | None = None
    expected_input: str | None = None
    input_mode: str | None = None
    voice_placeholder_text: str | None = None
    sentence_masked: str | None = None
    source_entry_type: str | None = None
    source_word_id: str | None = None
    source_meaning_id: str | None = None
    audio_state: str = "not_available"
    audio: ReviewPromptAudioPayload | None = None


class ReviewDetailMeaning(BaseModel):
    id: str
    definition: str
    example: str | None = None
    part_of_speech: str | None = None


class ReviewDetailResponse(BaseModel):
    entry_type: str
    entry_id: str
    display_text: str
    pronunciation: str | None = None
    pronunciations: dict[str, str] = {}
    part_of_speech: str | None = None
    primary_definition: str | None = None
    primary_example: str | None = None
    meaning_count: int = 0
    remembered_count: int = 0
    pro_tip: str | None = None
    compare_with: list[str] = []
    meanings: list[ReviewDetailMeaning] = []
    audio_state: str = "not_available"
    coverage_summary: str | None = None


class ScheduleOptionResponse(BaseModel):
    value: str
    label: str
    is_default: bool = False


class LearningStartCard(BaseModel):
    queue_item_id: str | None
    meaning_id: str
    word: str
    definition: str | None
    prompt: ReviewPrompt
    detail: ReviewDetailResponse | None = None


class LearningStartResponse(BaseModel):
    entry_type: str
    entry_id: str
    entry_word: str
    meaning_ids: list[str]
    queue_item_ids: list[str]
    cards: list[LearningStartCard]
    requires_lookup_hint: bool = False
    detail: ReviewDetailResponse | None = None
    schedule_options: list[ScheduleOptionResponse] = []


class QueueItemResponse(BaseModel):
    id: str
    session_id: str | None = None
    word_id: str | None = None
    meaning_id: str
    target_type: str | None = None
    target_id: str | None = None
    card_type: str | None = None
    quality_rating: int | None = None
    time_spent_ms: int | None = None
    ease_factor: float | None = None
    interval_days: int | None = None
    repetitions: int | None = None
    next_review: datetime | None = None
    review_count: int | None = None
    correct_count: int | None = None
    word: str | None = None
    definition: str | None = None
    review_mode: str | None = None
    prompt: dict[str, Any] | ReviewPrompt | None = None
    source_word_id: str | None = None
    source_meaning_id: str | None = None
    source_entry_type: str | None = None
    source_entry_id: str | None = None
    outcome: str | None = None
    needs_relearn: bool = False
    recheck_planned: bool = False
    detail: ReviewDetailResponse | None = None
    schedule_options: list[ScheduleOptionResponse] = []


class QueueStatsResponse(BaseModel):
    total_items: int
    due_items: int
    review_count: int
    correct_count: int
    accuracy: float


class QueueScheduleUpdateRequest(BaseModel):
    schedule_override: str = Field(..., max_length=32)

    @field_validator("schedule_override")
    @classmethod
    def validate_schedule_override(cls, value: str) -> str:
        if value not in ReviewService.SCHEDULE_OVERRIDE_VALUES:
            raise ValueError("Invalid schedule_override")
        return value


class QueueScheduleResponse(BaseModel):
    queue_item_id: str
    next_review_at: datetime | None = None
    current_schedule_value: str
    current_schedule_label: str
    current_schedule_source: str = "scheduled_timestamp"
    schedule_options: list[ScheduleOptionResponse] = []


class ReviewQueueSummaryBucketResponse(BaseModel):
    bucket: str
    count: int


class ReviewQueueSummaryResponse(BaseModel):
    generated_at: datetime
    total_count: int
    groups: list[ReviewQueueSummaryBucketResponse]


class ReviewQueueHistoryEventResponse(BaseModel):
    id: str
    reviewed_at: datetime
    outcome: str
    prompt_type: str
    prompt_family: str | None = None
    scheduled_by: str | None = None
    scheduled_interval_days: int | None = None


class GroupedQueueItemResponse(BaseModel):
    queue_item_id: str
    entry_id: str
    entry_type: str
    text: str
    status: str
    next_review_at: datetime | None = None
    last_reviewed_at: datetime | None = None
    success_streak: int = 0
    lapse_count: int = 0
    times_remembered: int = 0
    exposure_count: int = 0
    history: list[ReviewQueueHistoryEventResponse] = []


class GroupedQueueBucketResponse(BaseModel):
    bucket: str
    count: int
    items: list[GroupedQueueItemResponse]


class GroupedQueueResponse(BaseModel):
    generated_at: datetime
    total_count: int
    groups: list[GroupedQueueBucketResponse]


class AdminGroupedQueueItemResponse(GroupedQueueItemResponse):
    target_type: str | None = None
    target_id: str | None = None
    recheck_due_at: datetime | None = None
    next_due_at: datetime | None = None
    last_outcome: str | None = None
    relearning: bool | None = None
    relearning_trigger: str | None = None


class AdminGroupedQueueBucketResponse(BaseModel):
    bucket: str
    count: int
    items: list[AdminGroupedQueueItemResponse]


class ReviewQueueBucketDetailResponse(BaseModel):
    generated_at: datetime
    bucket: str
    count: int
    sort: str
    order: str
    items: list[GroupedQueueItemResponse]


class GroupedQueueDebugResponse(BaseModel):
    effective_now: str


class AdminReviewQueueSummaryResponse(BaseModel):
    generated_at: datetime
    total_count: int
    groups: list[ReviewQueueSummaryBucketResponse]
    debug: GroupedQueueDebugResponse


class AdminGroupedQueueResponse(BaseModel):
    generated_at: datetime
    total_count: int
    groups: list[AdminGroupedQueueBucketResponse]
    debug: GroupedQueueDebugResponse


class AdminReviewQueueBucketDetailResponse(BaseModel):
    generated_at: datetime
    bucket: str
    count: int
    sort: str
    order: str
    items: list[AdminGroupedQueueItemResponse]
    debug: GroupedQueueDebugResponse


class ReviewAnalyticsBucketResponse(BaseModel):
    value: str
    count: int


class ReviewAnalyticsSummaryResponse(BaseModel):
    days: int
    total_events: int
    audio_placeholder_events: int
    total_audio_replays: int = 0
    audio_replay_counts: list[ReviewAnalyticsBucketResponse] = []
    prompt_families: list[ReviewAnalyticsBucketResponse] = []
    outcomes: list[ReviewAnalyticsBucketResponse] = []
    response_input_modes: list[ReviewAnalyticsBucketResponse] = []


def _to_queue_item_response(
    item: Any,
    word: str | None = None,
    definition: str | None = None,
    review_mode: str | None = None,
    prompt: dict[str, Any] | ReviewPrompt | None = None,
    source_entry_type: str | None = None,
    source_entry_id: str | None = None,
    outcome: str | None = None,
    needs_relearn: bool = False,
    recheck_planned: bool = False,
    detail: dict[str, Any] | None = None,
    schedule_options: list[dict[str, Any]] | None = None,
) -> QueueItemResponse:
    item_meaning_id = getattr(item, "meaning_id", None)
    return QueueItemResponse(
        id=str(item.id),
        session_id=str(getattr(item, "session_id", ""))
        if getattr(item, "session_id", None)
        else None,
        word_id=str(getattr(item, "word_id", "")) if getattr(item, "word_id", None) else None,
        meaning_id=str(item_meaning_id) if item_meaning_id else "",
        target_type=getattr(item, "target_type", None),
        target_id=str(getattr(item, "target_id", "")) if getattr(item, "target_id", None) else None,
        card_type=getattr(item, "card_type", None),
        quality_rating=getattr(item, "quality_rating", None),
        time_spent_ms=getattr(item, "time_spent_ms", None),
        ease_factor=getattr(item, "ease_factor", None),
        interval_days=getattr(item, "interval_days", None),
        repetitions=getattr(item, "repetitions", None),
        next_review=getattr(item, "next_review", None),
        review_count=getattr(item, "review_count", None),
        correct_count=getattr(item, "correct_count", None),
        word=word,
        definition=definition,
        review_mode=review_mode,
        prompt=prompt,
        source_word_id=str(getattr(item, "word_id", "")) if getattr(item, "word_id", None) else None,
        source_meaning_id=str(item_meaning_id) if item_meaning_id else None,
        source_entry_type=source_entry_type,
        source_entry_id=source_entry_id,
        outcome=outcome,
        needs_relearn=needs_relearn,
        recheck_planned=recheck_planned,
        detail=ReviewDetailResponse(**detail) if detail else None,
        schedule_options=[ScheduleOptionResponse(**option) for option in (schedule_options or [])],
    )


@router.post("/queue", response_model=QueueItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_queue(
    request: QueueAddRequest,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Add a meaning to the user's review queue."""
    request_start = perf_counter()
    service = ReviewService(db)

    try:
        queue_item = await service.add_to_queue(current_user.id, request.meaning_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_add", **metrics)
    return _to_queue_item_response(queue_item)


@router.get("/queue/due", response_model=list[QueueItemResponse])
async def get_due_queue_items(
    limit: int = Query(default=20, ge=1, le=100),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QueueItemResponse]:
    """Get due items from the review queue with prompt metadata."""
    request_start = perf_counter()
    service = ReviewService(db)
    due_items = await service.get_due_queue_items(current_user.id, limit=limit, hydrate_limit=limit)

    items = [
        _to_queue_item_response(
            due_entry["item"],
            word=due_entry["word"],
            definition=due_entry["definition"],
            review_mode=due_entry.get("review_mode"),
            prompt=due_entry.get("prompt"),
            source_entry_type=due_entry.get("source_entry_type"),
            source_entry_id=due_entry.get("source_entry_id"),
            detail=due_entry.get("detail"),
            schedule_options=due_entry.get("schedule_options"),
        )
        for due_entry in due_items
    ]
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_due", result_count=len(items), **metrics)
    return items


@router.post("/queue/{item_id}/submit", response_model=QueueItemResponse)
async def submit_queue_review(
    item_id: uuid.UUID,
    request: QueueSubmitRequest,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Submit a review result for a queue item."""
    request_start = perf_counter()
    service = ReviewService(db)

    try:
        item = await service.submit_queue_review(
            item_id=item_id,
            quality=request.quality,
            confirm=request.confirm,
            time_spent_ms=request.time_spent_ms,
            audio_replay_count=request.audio_replay_count,
            card_type=request.card_type,
            prompt_token=request.prompt_token,
            review_mode=request.review_mode,
            outcome=request.outcome,
            prompt=request.prompt,
            selected_option_id=request.selected_option_id,
            typed_answer=request.typed_answer,
            schedule_override=request.schedule_override,
            user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_submit", **metrics)
    return _to_queue_item_response(
        item,
        outcome=getattr(item, "outcome", None),
        needs_relearn=bool(getattr(item, "needs_relearn", False)),
        recheck_planned=bool(getattr(item, "recheck_planned", False)),
        detail=getattr(item, "detail", None),
        schedule_options=getattr(item, "schedule_options", None),
    )


@router.put("/queue/{item_id}/schedule", response_model=QueueScheduleResponse)
async def update_queue_schedule(
    item_id: uuid.UUID,
    request: QueueScheduleUpdateRequest,
    http_request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueScheduleResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    try:
        payload = await service.update_queue_item_schedule(
            user_id=current_user.id,
            item_id=item_id,
            schedule_override=request.schedule_override,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        http_request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_schedule_update", **metrics)
    return QueueScheduleResponse(
        queue_item_id=payload["queue_item_id"],
        next_review_at=datetime.fromisoformat(payload["next_review_at"]) if payload["next_review_at"] else None,
        current_schedule_value=payload["current_schedule_value"],
        current_schedule_label=payload["current_schedule_label"],
        current_schedule_source=payload.get("current_schedule_source", "scheduled_timestamp"),
        schedule_options=[ScheduleOptionResponse(**option) for option in payload["schedule_options"]],
    )


@router.post(
    "/entry/{entry_type}/{entry_id}/learning/start",
    response_model=LearningStartResponse,
)
async def start_learning_entry(
    entry_type: str,
    entry_id: uuid.UUID,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LearningStartResponse:
    """Start a per-entry learning flow and return all cards for review."""
    request_start = perf_counter()
    service = ReviewService(db)

    try:
        payload = await service.start_learning_entry(
            user_id=current_user.id,
            entry_type=entry_type,
            entry_id=entry_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="learning_start", **metrics)
    return LearningStartResponse(**payload)


@router.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueStatsResponse:
    """Get queue-level review stats for the current user."""
    request_start = perf_counter()
    service = ReviewService(db)
    stats = await service.get_queue_stats(current_user.id)
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_stats", **metrics)
    return QueueStatsResponse(**stats)


@router.get("/queue/grouped", response_model=GroupedQueueResponse)
async def get_grouped_review_queue(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GroupedQueueResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    payload = await service.get_grouped_review_queue(
        user_id=current_user.id,
        now=datetime.now().astimezone(),
        include_debug_fields=False,
    )
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_grouped", **metrics)
    return GroupedQueueResponse(**payload)


@router.get("/admin/queue/grouped", response_model=AdminGroupedQueueResponse)
async def get_grouped_review_queue_admin(
    effective_now: datetime | None = Query(default=None),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminGroupedQueueResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    resolved_now = service._normalize_bucket_datetime(effective_now) or datetime.now().astimezone()
    payload = await service.get_grouped_review_queue(
        user_id=current_user.id,
        now=resolved_now,
        include_debug_fields=True,
    )
    payload["debug"] = {"effective_now": resolved_now.isoformat()}
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_grouped_admin", **metrics)
    return AdminGroupedQueueResponse(**payload)


@router.get("/queue/summary", response_model=ReviewQueueSummaryResponse)
async def get_review_queue_summary(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueSummaryResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    payload = await service.get_grouped_review_queue_summary(
        user_id=current_user.id,
        now=datetime.now().astimezone(),
    )
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_summary", **metrics)
    return ReviewQueueSummaryResponse(**payload)


@router.get("/queue/buckets/{bucket}", response_model=ReviewQueueBucketDetailResponse)
async def get_review_queue_bucket_detail(
    bucket: str,
    sort: str = Query(default="next_review_at"),
    order: str = Query(default="asc"),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueBucketDetailResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    try:
        payload = await service.get_grouped_review_queue_bucket_detail(
            user_id=current_user.id,
            now=datetime.now().astimezone(),
            bucket=bucket,
            sort=sort,
            order=order,
            include_debug_fields=False,
        )
    except ValueError as e:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "bucket" in str(e).lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_bucket_detail", **metrics)
    return ReviewQueueBucketDetailResponse(**payload)


@router.get("/admin/queue/summary", response_model=AdminReviewQueueSummaryResponse)
async def get_review_queue_summary_admin(
    effective_now: datetime | None = Query(default=None),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminReviewQueueSummaryResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    resolved_now = service._normalize_bucket_datetime(effective_now) or datetime.now().astimezone()
    payload = await service.get_grouped_review_queue_summary(
        user_id=current_user.id,
        now=resolved_now,
    )
    payload["debug"] = {"effective_now": resolved_now.isoformat()}
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_summary_admin", **metrics)
    return AdminReviewQueueSummaryResponse(**payload)


@router.get("/admin/queue/buckets/{bucket}", response_model=AdminReviewQueueBucketDetailResponse)
async def get_review_queue_bucket_detail_admin(
    bucket: str,
    sort: str = Query(default="next_review_at"),
    order: str = Query(default="asc"),
    effective_now: datetime | None = Query(default=None),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> AdminReviewQueueBucketDetailResponse:
    request_start = perf_counter()
    service = ReviewService(db)
    resolved_now = service._normalize_bucket_datetime(effective_now) or datetime.now().astimezone()
    try:
        payload = await service.get_grouped_review_queue_bucket_detail(
            user_id=current_user.id,
            now=resolved_now,
            bucket=bucket,
            sort=sort,
            order=order,
            include_debug_fields=True,
        )
    except ValueError as e:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "bucket" in str(e).lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=status_code, detail=str(e))

    payload["debug"] = {"effective_now": resolved_now.isoformat()}
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_bucket_detail_admin", **metrics)
    return AdminReviewQueueBucketDetailResponse(**payload)


@router.get("/queue/{item_id}", response_model=QueueItemResponse)
async def get_queue_item(
    item_id: uuid.UUID,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Get a fully hydrated queue item for the current user."""
    request_start = perf_counter()
    service = ReviewService(db)
    try:
        due_entry = await service.get_queue_item(current_user.id, item_id=item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="queue_item", **metrics)
    return _to_queue_item_response(
        due_entry["item"],
        word=due_entry["word"],
        definition=due_entry["definition"],
        review_mode=due_entry.get("review_mode"),
        prompt=due_entry.get("prompt"),
        source_entry_type=due_entry.get("source_entry_type"),
        source_entry_id=due_entry.get("source_entry_id"),
        detail=due_entry.get("detail"),
        schedule_options=due_entry.get("schedule_options"),
    )


@router.get("/analytics/summary", response_model=ReviewAnalyticsSummaryResponse)
async def get_review_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    request: Request = None,
    response: Response = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewAnalyticsSummaryResponse:
    """Get a lightweight summary of recent entry-review analytics for the current user."""
    request_start = perf_counter()
    service = ReviewService(db)
    summary = await service.get_review_analytics_summary(current_user.id, days=days)
    metrics = finalize_request_db_metrics(
        response,
        request,
        header_prefix="X-Reviews",
        request_start=request_start,
    )
    logger.info("reviews_request", route_name="analytics_summary", **metrics)
    return ReviewAnalyticsSummaryResponse(**summary)
