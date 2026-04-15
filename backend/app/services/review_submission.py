from __future__ import annotations

from datetime import date, datetime, timezone
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.entry_review import EntryReviewState
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.spaced_repetition import calculate_next_review
from app.services.review_srs_v1 import (
    REVIEW_SRS_V1_BUCKETS,
    build_schedule_options,
    bucket_for_interval_days,
    cadence_step_for_bucket,
    interval_days_for_bucket,
    resolve_bucket_after_review,
)
from app.services.review_schedule import recheck_due_at_for_retry

if TYPE_CHECKING:
    from app.services.review import ReviewService


async def build_entry_state_detail(
    service: "ReviewService",
    *,
    user_id: uuid.UUID,
    entry_state: EntryReviewState,
) -> dict[str, Any] | None:
    if entry_state.entry_type == "word":
        return await service._build_detail_payload_for_word_id(
            user_id=user_id,
            word_id=entry_state.entry_id,
        )

    phrase_result = await service.db.execute(
        select(PhraseEntry).where(PhraseEntry.id == entry_state.entry_id)
    )
    phrase = phrase_result.scalar_one_or_none()
    senses_result = await service.db.execute(
        select(PhraseSense)
        .where(PhraseSense.phrase_entry_id == entry_state.entry_id)
        .order_by(PhraseSense.order_index.asc())
    )
    senses = senses_result.scalars().all()
    if phrase is None or not senses:
        return None
    return await service._build_phrase_detail_payload(user_id=user_id, phrase=phrase, senses=senses)


def _sync_entry_state_srs_fields(entry_state: EntryReviewState, interval_days: int) -> None:
    entry_state.srs_bucket = bucket_for_interval_days(interval_days)
    entry_state.cadence_step = cadence_step_for_bucket(entry_state.srs_bucket)


def _current_bucket_for_entry_state(entry_state: EntryReviewState) -> str:
    explicit_bucket = (getattr(entry_state, "srs_bucket", None) or "").strip()
    if explicit_bucket in REVIEW_SRS_V1_BUCKETS:
        return explicit_bucket
    interval_days = getattr(entry_state, "interval_days", None)
    if isinstance(interval_days, int) and interval_days > 0:
        return bucket_for_interval_days(interval_days)
    return bucket_for_interval_days(int(round(float(entry_state.stability or 1))))


async def _load_or_create_learner_status(
    service: "ReviewService",
    *,
    user_id: uuid.UUID,
    entry_state: EntryReviewState,
) -> LearnerEntryStatus:
    status_result = await service.db.execute(
        select(LearnerEntryStatus).where(
            LearnerEntryStatus.user_id == user_id,
            LearnerEntryStatus.entry_type == entry_state.entry_type,
            LearnerEntryStatus.entry_id == entry_state.entry_id,
        )
    )
    learner_status = status_result.scalar_one_or_none()
    if learner_status is not None:
        return learner_status
    learner_status = LearnerEntryStatus(
        user_id=user_id,
        entry_type=entry_state.entry_type,
        entry_id=entry_state.entry_id,
        status="learning",
    )
    service.db.add(learner_status)
    await service.db.flush()
    return learner_status


def apply_entry_state_review_result(
    service: "ReviewService",
    *,
    entry_state: EntryReviewState,
    review_result: Any,
    resolved_outcome: str,
    prompt: dict[str, Any] | None,
    resolved_bucket: str,
    resolved_interval_days: int | None,
    resolved_next_review: datetime | None,
    reviewed_at: datetime,
    user_timezone: str,
    due_review_date: date | None,
    min_due_at_utc: datetime | None,
) -> None:
    entry_state.stability = max(0.15, float(resolved_interval_days or review_result.stability))
    entry_state.difficulty = review_result.difficulty
    entry_state.last_prompt_type = (prompt or {}).get("prompt_type")
    entry_state.last_outcome = resolved_outcome
    entry_state.is_fragile = review_result.is_fragile
    entry_state.last_reviewed_at = reviewed_at
    entry_state.srs_bucket = resolved_bucket
    entry_state.cadence_step = cadence_step_for_bucket(resolved_bucket)
    entry_state.due_review_date = due_review_date
    entry_state.min_due_at_utc = min_due_at_utc
    entry_state.exposure_count = int(entry_state.exposure_count or 0) + 1
    if resolved_outcome in {"correct_tested", "remember"}:
        entry_state.success_streak = int(entry_state.success_streak or 0) + 1
        entry_state.times_remembered = int(entry_state.times_remembered or 0) + 1
        entry_state.relearning = False
        entry_state.relearning_trigger = None
        entry_state.recheck_due_at = None
        return

    entry_state.success_streak = 0
    if resolved_outcome == "wrong":
        entry_state.lapse_count = int(entry_state.lapse_count or 0) + 1
    entry_state.relearning = True
    entry_state.relearning_trigger = resolved_outcome
    entry_state.recheck_due_at = recheck_due_at_for_retry(
        reviewed_at_utc=reviewed_at,
        user_timezone=user_timezone,
    )


async def submit_entry_state_review(
    service: "ReviewService",
    *,
    entry_state: EntryReviewState,
    quality: int,
    time_spent_ms: int,
    user_id: uuid.UUID,
    confirm: bool,
    prompt_token: str | None,
    review_mode: str | None,
    outcome: str | None,
    selected_option_id: str | None,
    typed_answer: str | None,
    audio_replay_count: int,
    prompt: dict[str, Any] | None,
    schedule_override: str | None,
) -> EntryReviewState:
    prompt_token_payload = service._decode_prompt_token(prompt_token)
    if prompt_token_payload is None:
        raise ValueError("Invalid prompt token")
    if prompt_token_payload.get("queue_item_id") not in {None, str(entry_state.id)}:
        raise ValueError("Prompt token does not match queue item")
    if prompt_token_payload.get("user_id") not in {None, str(user_id)}:
        raise ValueError("Prompt token does not match user")

    prompt_id = str(prompt_token_payload.get("prompt_id") or "")
    issued_at_raw = prompt_token_payload.get("issued_at")
    if prompt_id and prompt_id != getattr(entry_state, "last_submission_prompt_id", None):
        if isinstance(issued_at_raw, str) and entry_state.last_reviewed_at is not None:
            try:
                issued_at = datetime.fromisoformat(issued_at_raw)
            except ValueError:
                issued_at = None
            if issued_at is not None:
                if issued_at.tzinfo is None:
                    issued_at = issued_at.replace(tzinfo=timezone.utc)
                if issued_at <= entry_state.last_reviewed_at:
                    raise ValueError("Prompt submission is stale")
    if prompt_id and getattr(entry_state, "last_submission_prompt_id", None) == prompt_id:
        if schedule_override:
            reviewed_at = service._schedule_anchor_reviewed_at(
                state=entry_state,
                fallback_now=datetime.now(timezone.utc),
            )
            current_interval_days = int(getattr(entry_state, "interval_days", 0) or 0)
            current_due_review_date = getattr(entry_state, "due_review_date", None)
            current_min_due_at_utc = getattr(entry_state, "min_due_at_utc", None)
            last_outcome = getattr(entry_state, "last_outcome", None)
            if last_outcome is not None and last_outcome not in {"correct_tested", "remember"}:
                raise ValueError("schedule_override is only allowed after success")
            current_bucket = _current_bucket_for_entry_state(entry_state)
            if schedule_override == "known" and not (
                current_bucket == "known"
                or (
                    current_bucket == "180d"
                    and getattr(entry_state, "last_prompt_type", None)
                    in service.PROMPT_TYPE_OPTIONS
                    and getattr(entry_state, "last_outcome", None) == "correct_tested"
                        and getattr(entry_state, "last_prompt_type", None)
                        != service.PROMPT_TYPE_CONFIDENCE_CHECK
                    )
                ):
                raise ValueError("known override requires objective success at 180d")
            (
                resolved_interval_days,
                resolved_due_review_date,
                resolved_min_due_at_utc,
                resolved_bucket,
            ) = await service._resolve_official_review_schedule(
                user_id=user_id,
                reviewed_at=reviewed_at,
                resolved_bucket=schedule_override or current_bucket,
                resolved_outcome=getattr(entry_state, "last_outcome", None),
                schedule_override=schedule_override,
            )
            if (
                resolved_interval_days != current_interval_days
                or resolved_due_review_date != current_due_review_date
                or resolved_min_due_at_utc != current_min_due_at_utc
            ):
                entry_state.interval_days = resolved_interval_days
                entry_state.due_review_date = resolved_due_review_date
                entry_state.min_due_at_utc = resolved_min_due_at_utc
                entry_state.next_review = resolved_min_due_at_utc
                entry_state.srs_bucket = resolved_bucket
                entry_state.cadence_step = cadence_step_for_bucket(resolved_bucket)
                entry_state.schedule_options = build_schedule_options(resolved_bucket)
                learner_status = await _load_or_create_learner_status(
                    service,
                    user_id=user_id,
                    entry_state=entry_state,
                )
                learner_status.status = "known" if resolved_bucket == "known" else "learning"
                await service.db.commit()
        entry_state.detail = getattr(entry_state, "detail", None) or await build_entry_state_detail(
            service,
            user_id=user_id,
            entry_state=entry_state,
        )
        if getattr(entry_state, "last_outcome", None) in {"lookup", "wrong"}:
            entry_state.schedule_options = []
        else:
            entry_state.schedule_options = getattr(entry_state, "schedule_options", None) or build_schedule_options(
                _current_bucket_for_entry_state(entry_state)
            )
        return entry_state

    normalized_review_mode = service._resolve_submit_review_mode_from_prompt_token(
        prompt_token_payload=prompt_token_payload
    )
    resolved_outcome = service._resolve_submit_outcome_from_prompt_token(
        prompt_token_payload=prompt_token_payload,
        outcome=outcome,
        selected_option_id=selected_option_id,
        typed_answer=typed_answer,
    )
    prompt_type = str(
        prompt_token_payload.get("prompt_type") or service.PROMPT_TYPE_DEFINITION_TO_ENTRY
    )
    source_target_id = service._parse_optional_uuid(prompt_token_payload.get("source_meaning_id"))
    if source_target_id is not None:
        entry_state.target_id = source_target_id
        entry_state.meaning_id = source_target_id
    entry_state.target_type = "meaning" if entry_state.entry_type == "word" else "phrase_sense"
    current_bucket = _current_bucket_for_entry_state(entry_state)
    recommended_bucket = resolve_bucket_after_review(current_bucket, prompt_type, resolved_outcome)
    review_result = calculate_next_review(
        outcome=resolved_outcome,
        prompt_type=prompt_type,
        stability=float(entry_state.stability or 0.3),
        difficulty=float(entry_state.difficulty or 0.5),
        grade=service._derive_review_grade(
            outcome=resolved_outcome,
            prompt={"prompt_type": prompt_token_payload.get("prompt_type")},
            quality=quality,
            time_spent_ms=time_spent_ms,
        ),
    )
    preview_bucket = schedule_override or recommended_bucket
    if schedule_override and resolved_outcome not in {"correct_tested", "remember"}:
        raise ValueError("schedule_override is only allowed after success")
    if schedule_override == "known" and recommended_bucket != "known":
        raise ValueError("known override requires objective success at 180d")

    if resolved_outcome in {"correct_tested", "remember"} and not confirm:
        detail = await build_entry_state_detail(
            service,
            user_id=user_id,
            entry_state=entry_state,
        )
        entry_state.outcome = resolved_outcome
        entry_state.needs_relearn = False
        entry_state.recheck_planned = False
        entry_state.detail = detail
        entry_state.interval_days = interval_days_for_bucket(preview_bucket)
        entry_state.srs_bucket = preview_bucket
        entry_state.cadence_step = cadence_step_for_bucket(preview_bucket)
        entry_state.schedule_options = build_schedule_options(preview_bucket)
        return entry_state

    reviewed_at = datetime.now(timezone.utc)
    scheduled_by = "manual_override" if schedule_override else "recommended"
    prefs = await service._get_user_review_preferences(user_id)
    user_timezone = service._resolve_user_timezone(getattr(prefs, "timezone", None))
    (
        resolved_interval_days,
        resolved_due_review_date,
        resolved_min_due_at_utc,
        resolved_bucket,
    ) = await service._resolve_official_review_schedule(
        user_id=user_id,
        reviewed_at=reviewed_at,
        resolved_bucket=preview_bucket,
        resolved_outcome=resolved_outcome,
        schedule_override=schedule_override,
    )

    apply_entry_state_review_result(
        service,
        entry_state=entry_state,
        review_result=review_result,
        resolved_outcome=resolved_outcome,
        prompt={"prompt_type": prompt_type},
        resolved_bucket=resolved_bucket,
        resolved_interval_days=resolved_interval_days,
        resolved_next_review=resolved_min_due_at_utc,
        reviewed_at=reviewed_at,
        user_timezone=user_timezone,
        due_review_date=resolved_due_review_date,
        min_due_at_utc=resolved_min_due_at_utc,
    )
    detail = await build_entry_state_detail(
        service,
        user_id=user_id,
        entry_state=entry_state,
    )
    await service._record_entry_review_event(
        user_id=user_id,
        state=entry_state,
        target_type=entry_state.target_type
        or ("meaning" if entry_state.entry_type == "word" else "phrase_sense"),
        target_id=entry_state.target_id
        or service._parse_optional_uuid(prompt_token_payload.get("source_meaning_id")),
        prompt_type=prompt_type,
        outcome=resolved_outcome,
        selected_option_id=selected_option_id,
        typed_answer=typed_answer,
        audio_replay_count=audio_replay_count,
        scheduled_interval_days=resolved_interval_days,
        scheduled_by=scheduled_by,
        time_spent_ms=time_spent_ms,
        prompt={"input_mode": prompt_token_payload.get("input_mode")},
    )
    entry_state.quality_rating = service._derive_quality(
        review_mode=normalized_review_mode,
        quality=quality,
        prompt={
            "prompt_type": prompt_token_payload.get("prompt_type"),
            "expected_input": prompt_token_payload.get("expected_input"),
            "source_entry_type": prompt_token_payload.get("source_entry_type"),
            "options": [
                {
                    "option_id": prompt_token_payload.get("correct_option_id"),
                    "is_correct": True,
                }
            ]
            if prompt_token_payload.get("correct_option_id")
            else [],
        },
        selected_option_id=selected_option_id,
        typed_answer=typed_answer,
    )
    entry_state.time_spent_ms = time_spent_ms
    entry_state.interval_days = resolved_interval_days
    entry_state.outcome = resolved_outcome
    entry_state.needs_relearn = resolved_outcome in {"lookup", "wrong"}
    entry_state.recheck_planned = resolved_outcome in {"lookup", "wrong"}
    entry_state.last_submission_prompt_id = prompt_id or None
    entry_state.detail = detail
    entry_state.schedule_options = (
        build_schedule_options(resolved_bucket)
        if resolved_outcome in {"correct_tested", "remember"}
        else []
    )
    learner_status = await _load_or_create_learner_status(
        service,
        user_id=user_id,
        entry_state=entry_state,
    )
    learner_status.status = "known" if resolved_bucket == "known" else "learning"
    await service.db.commit()
    return entry_state

async def submit_queue_review(
    service: "ReviewService",
    *,
    item_id: uuid.UUID,
    quality: int,
    time_spent_ms: int,
    user_id: uuid.UUID,
    confirm: bool = False,
    card_type: str | None = None,
    prompt_token: str | None = None,
    review_mode: str | None = None,
    outcome: str | None = None,
    selected_option_id: str | None = None,
    typed_answer: str | None = None,
    audio_replay_count: int = 0,
    prompt: dict[str, Any] | None = None,
    schedule_override: str | None = None,
) -> Any:
    state_lookup = await service.db.execute(
        select(EntryReviewState).where(
            EntryReviewState.id == item_id,
            EntryReviewState.user_id == user_id,
        ).with_for_update()
    )
    entry_state = state_lookup.scalar_one_or_none()
    if isinstance(entry_state, EntryReviewState):
        return await submit_entry_state_review(
            service,
            entry_state=entry_state,
            quality=quality,
            time_spent_ms=time_spent_ms,
            user_id=user_id,
            confirm=confirm,
            prompt_token=prompt_token,
            review_mode=review_mode,
            outcome=outcome,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
            audio_replay_count=audio_replay_count,
            prompt=prompt,
            schedule_override=schedule_override,
        )

    raise ValueError(f"Queue item {item_id} not found")
