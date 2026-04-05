from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.entry_review import EntryReviewState
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.spaced_repetition import calculate_next_review

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


def apply_entry_state_review_result(
    service: "ReviewService",
    *,
    entry_state: EntryReviewState,
    review_result: Any,
    resolved_outcome: str,
    prompt: dict[str, Any] | None,
    resolved_interval_days: int,
    resolved_next_review: datetime,
) -> None:
    now = datetime.now(timezone.utc)
    entry_state.stability = max(0.15, float(resolved_interval_days or review_result.stability))
    entry_state.difficulty = review_result.difficulty
    entry_state.last_prompt_type = (prompt or {}).get("prompt_type")
    entry_state.last_outcome = resolved_outcome
    entry_state.is_fragile = review_result.is_fragile
    entry_state.last_reviewed_at = now
    entry_state.next_due_at = resolved_next_review
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
    entry_state.recheck_due_at = now + timedelta(minutes=10)


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
    if prompt_id and getattr(entry_state, "last_submission_prompt_id", None) == prompt_id:
        if schedule_override:
            current_interval_days = int(getattr(entry_state, "interval_days", 0) or 0)
            current_next_due_at = getattr(entry_state, "next_due_at", None)
            resolved_interval_days, resolved_next_review, _ = service._derive_interval_from_override(
                original_interval_days=current_interval_days,
                override_value=schedule_override,
                base_next_review=current_next_due_at,
            )
            if (
                resolved_interval_days != current_interval_days
                or (
                    current_next_due_at is not None
                    and resolved_next_review != current_next_due_at
                )
            ):
                entry_state.interval_days = resolved_interval_days
                entry_state.next_due_at = resolved_next_review
                entry_state.schedule_options = service._build_schedule_options(
                    resolved_interval_days
                )
                await service.db.commit()
        entry_state.detail = getattr(entry_state, "detail", None) or await build_entry_state_detail(
            service,
            user_id=user_id,
            entry_state=entry_state,
        )
        entry_state.schedule_options = getattr(entry_state, "schedule_options", None) or service._build_schedule_options(
            int(getattr(entry_state, "interval_days", 0) or 0)
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
    review_result = calculate_next_review(
        outcome=resolved_outcome,
        prompt_type=str(
            prompt_token_payload.get("prompt_type") or service.PROMPT_TYPE_DEFINITION_TO_ENTRY
        ),
        stability=float(entry_state.stability or 0.3),
        difficulty=float(entry_state.difficulty or 0.5),
        grade=service._derive_review_grade(
            outcome=resolved_outcome,
            prompt={
                "prompt_type": prompt_token_payload.get("prompt_type"),
            },
            quality=quality,
            time_spent_ms=time_spent_ms,
        ),
    )
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
        entry_state.schedule_options = service._build_schedule_options(review_result.interval_days)
        return entry_state

    scheduled_by = "manual_override" if schedule_override else "recommended"
    resolved_interval_days, resolved_next_review, _ = service._derive_interval_from_override(
        original_interval_days=review_result.interval_days,
        override_value=schedule_override,
        base_next_review=review_result.next_review,
    )

    apply_entry_state_review_result(
        service,
        entry_state=entry_state,
        review_result=review_result,
        resolved_outcome=resolved_outcome,
        prompt={"prompt_type": prompt_token_payload.get("prompt_type")},
        resolved_interval_days=resolved_interval_days,
        resolved_next_review=resolved_next_review,
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
        prompt_type=str(
            prompt_token_payload.get("prompt_type") or service.PROMPT_TYPE_DEFINITION_TO_ENTRY
        ),
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
    entry_state.target_type = entry_state.target_type or (
        "meaning" if entry_state.entry_type == "word" else "phrase_sense"
    )
    entry_state.target_id = entry_state.target_id or service._parse_optional_uuid(
        prompt_token_payload.get("source_meaning_id")
    )
    entry_state.last_submission_prompt_id = prompt_id or None
    entry_state.detail = detail
    entry_state.schedule_options = service._build_schedule_options(resolved_interval_days)
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
