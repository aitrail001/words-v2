from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from app.services.review_srs_v1 import (
    cadence_step_for_bucket,
    normalize_review_mode,
    select_cadence_family,
)

if TYPE_CHECKING:
    from app.services.review import ReviewService


def _resolve_v1_bucket_and_step(
    *,
    srs_bucket: str | None,
    cadence_step: int | None,
) -> tuple[str, int]:
    bucket = (srs_bucket or "1d").strip() or "1d"
    try:
        resolved_step = cadence_step_for_bucket(bucket) if cadence_step is None else int(cadence_step)
        select_cadence_family("standard", bucket, resolved_step)
    except (TypeError, ValueError):
        return "1d", 0
    return bucket, resolved_step


def _build_v1_deep_hard_prompt_types(
    service: "ReviewService",
    *,
    sentence: str | None,
    bucket: str,
    allow_typed_recall: bool,
    allow_audio_spelling: bool,
) -> list[str]:
    hard_prompt_types: list[str] = []
    stage_two_typed_buckets = {"7d", "14d"}
    stage_three_buckets = {"30d", "90d", "180d", "known"}

    if bucket in stage_two_typed_buckets and allow_typed_recall:
        hard_prompt_types.append(service.PROMPT_TYPE_TYPED_RECALL)
    if bucket in stage_three_buckets and allow_typed_recall:
        hard_prompt_types.append(service.PROMPT_TYPE_TYPED_RECALL)
    if sentence:
        hard_prompt_types.append(service.PROMPT_TYPE_SENTENCE_GAP)
    if bucket in stage_three_buckets and allow_audio_spelling:
        if bucket == "180d":
            hard_prompt_types = [
                service.PROMPT_TYPE_SPEAK_RECALL,
                *[item for item in hard_prompt_types if item != service.PROMPT_TYPE_SPEAK_RECALL],
            ]
        else:
            hard_prompt_types.append(service.PROMPT_TYPE_SPEAK_RECALL)
    if bucket == "90d" and allow_typed_recall:
        # Rotate the later-stage hard-first ordering without randomness.
        hard_prompt_types = [
            service.PROMPT_TYPE_TYPED_RECALL,
            *[item for item in hard_prompt_types if item != service.PROMPT_TYPE_TYPED_RECALL],
        ]
    return hard_prompt_types


async def resolve_prompt_preferences(
    service: "ReviewService",
    user_id: uuid.UUID | None,
) -> dict[str, Any]:
    prefs = await service._get_user_review_preferences(user_id) if user_id is not None else None
    review_depth_preset = service._normalize_review_depth_preset(
        getattr(prefs, "review_depth_preset", None)
    )
    normalized_mode = normalize_review_mode(review_depth_preset)
    return {
        "prefs": prefs,
        "review_depth_preset": review_depth_preset,
        "allow_typed_recall": normalized_mode == "deep",
        "allow_audio_spelling": normalized_mode == "deep",
        "allow_confidence": True,
    }


def build_available_prompt_types(
    service: "ReviewService",
    *,
    review_mode: str,
    sentence: str | None,
    alternative_definitions: list[str] | None,
    review_depth_preset: str,
    allow_typed_recall: bool,
    allow_audio_spelling: bool,
    allow_confidence: bool,
    active_target_count: int,
    srs_bucket: str | None = None,
    cadence_step: int | None = None,
) -> list[str]:
    del alternative_definitions, active_target_count

    if review_mode == service.REVIEW_MODE_CONFIDENCE:
        if sentence and allow_confidence:
            return [service.PROMPT_TYPE_CONFIDENCE_CHECK]
        return [service.PROMPT_TYPE_DEFINITION_TO_ENTRY]

    bucket, step = _resolve_v1_bucket_and_step(
        srs_bucket=srs_bucket,
        cadence_step=cadence_step,
    )
    normalized_mode = normalize_review_mode(review_depth_preset)
    cadence_family = select_cadence_family(normalized_mode, bucket, step)

    simple_prompt_types = [
        service.PROMPT_TYPE_ENTRY_TO_DEFINITION,
        service.PROMPT_TYPE_AUDIO_TO_DEFINITION,
        service.PROMPT_TYPE_DEFINITION_TO_ENTRY,
    ]
    if sentence and allow_confidence:
        simple_prompt_types.append(service.PROMPT_TYPE_CONFIDENCE_CHECK)

    hard_prompt_types: list[str] = []
    if normalized_mode == "deep":
        hard_prompt_types = _build_v1_deep_hard_prompt_types(
            service,
            sentence=sentence,
            bucket=bucket,
            allow_typed_recall=allow_typed_recall,
            allow_audio_spelling=allow_audio_spelling,
        )
    elif sentence:
        hard_prompt_types.append(service.PROMPT_TYPE_SENTENCE_GAP)

    if cadence_family == "hard" and hard_prompt_types:
        return hard_prompt_types
    return simple_prompt_types


async def load_entry_target_distractors(
    service: "ReviewService",
    *,
    prompt_type: str,
    user_id: uuid.UUID | None,
    source_entry_id: uuid.UUID | None,
    source_text: str,
    normalized_entry_type: str,
    is_phrase_entry: bool,
) -> list[str]:
    if (
        prompt_type == service.PROMPT_TYPE_DEFINITION_TO_ENTRY
        and normalized_entry_type == "word"
        and source_entry_id is not None
    ):
        primary = await service._fetch_word_confusable_distractors(
            target_entry_id=source_entry_id,
            limit=3,
        )
        fallback: list[str] = []
        if len(primary) < 3:
            if user_id is not None:
                fallback = await service._fetch_same_day_entry_distractors(
                    user_id=user_id,
                    target_entry_id=source_entry_id,
                    target_entry_type=normalized_entry_type,
                    limit=3,
                )
            if len(service._merge_distractor_candidates(exclude=source_text, primary=primary, fallback=fallback, limit=3)) < 3:
                adjacent = await service._fetch_adjacent_entry_distractors(
                    target_entry_id=source_entry_id,
                    target_entry_type=normalized_entry_type,
                    limit=3,
                )
                fallback = [*fallback, *adjacent]
        return service._merge_distractor_candidates(
            exclude=source_text,
            primary=primary,
            fallback=fallback,
            limit=3,
        )

    if user_id is not None and source_entry_id is not None:
        same_day = await service._fetch_same_day_entry_distractors(
            user_id=user_id,
            target_entry_id=source_entry_id,
            target_entry_type=normalized_entry_type,
            limit=3,
        )
        fallback: list[str] = []
        if len(service._merge_distractor_candidates(exclude=source_text, primary=same_day, fallback=[], limit=3)) < 3:
            fallback = await service._fetch_adjacent_entry_distractors(
                target_entry_id=source_entry_id,
                target_entry_type=normalized_entry_type,
                limit=3,
            )
        return service._merge_distractor_candidates(
            exclude=source_text,
            primary=same_day,
            fallback=fallback,
            limit=3,
        )

    if is_phrase_entry:
        return await service._fetch_phrase_distractors(correct_phrase=source_text, limit=3)
    return await service._fetch_word_distractors(correct_word=source_text, limit=3)


async def load_definition_target_distractors(
    service: "ReviewService",
    *,
    user_id: uuid.UUID | None,
    source_entry_id: uuid.UUID | None,
    definition: str,
    meaning_id: uuid.UUID,
    normalized_entry_type: str,
) -> list[str]:
    if user_id is not None and source_entry_id is not None:
        same_day = await service._fetch_same_day_definition_distractors(
            user_id=user_id,
            target_meaning_id=meaning_id,
            target_entry_type=normalized_entry_type,
            limit=3,
        )
        fallback: list[str] = []
        if len(service._merge_distractor_candidates(exclude=definition, primary=same_day, fallback=[], limit=3)) < 3:
            fallback = await service._fetch_adjacent_definition_distractors(
                target_meaning_id=meaning_id,
                target_entry_type=normalized_entry_type,
                limit=3,
            )
        return service._merge_distractor_candidates(
            exclude=definition,
            primary=same_day,
            fallback=fallback,
            limit=3,
        )
    return await service._fetch_definition_distractors(
        correct_meaning_id=meaning_id,
        limit=3,
    )


async def load_prompt_distractors(
    service: "ReviewService",
    *,
    prompt_type: str,
    user_id: uuid.UUID | None,
    source_entry_id: uuid.UUID | None,
    source_text: str,
    definition: str,
    meaning_id: uuid.UUID,
    normalized_entry_type: str,
    is_phrase_entry: bool,
) -> list[str]:
    entry_target_prompt_types = {
        service.PROMPT_TYPE_DEFINITION_TO_ENTRY,
        service.PROMPT_TYPE_SENTENCE_GAP,
        service.PROMPT_TYPE_COLLOCATION_CHECK,
        service.PROMPT_TYPE_SITUATION_MATCHING,
    }
    if prompt_type in entry_target_prompt_types:
        distractors = await load_entry_target_distractors(
            service,
            prompt_type=prompt_type,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_text=source_text,
            normalized_entry_type=normalized_entry_type,
            is_phrase_entry=is_phrase_entry,
        )
        if prompt_type in {service.PROMPT_TYPE_COLLOCATION_CHECK, service.PROMPT_TYPE_SITUATION_MATCHING}:
            return service._rank_entry_distractors(
                correct_text=source_text,
                candidates=distractors,
                contextual=True,
            )[:3]
        return distractors

    if prompt_type in {
        service.PROMPT_TYPE_CONFIDENCE_CHECK,
        service.PROMPT_TYPE_MEANING_DISCRIMINATION,
        service.PROMPT_TYPE_TYPED_RECALL,
        service.PROMPT_TYPE_SPEAK_RECALL,
    }:
        return []

    return await load_definition_target_distractors(
        service,
        user_id=user_id,
        source_entry_id=source_entry_id,
        definition=definition,
        meaning_id=meaning_id,
        normalized_entry_type=normalized_entry_type,
    )


async def load_prompt_audio_for_type(
    service: "ReviewService",
    *,
    prompt_type: str,
    user_id: uuid.UUID | None,
    source_entry_id: uuid.UUID | None,
    source_entry_type: str,
    meaning_id: uuid.UUID,
) -> dict[str, Any] | None:
    if prompt_type not in {
        service.PROMPT_TYPE_AUDIO_TO_DEFINITION,
        service.PROMPT_TYPE_CONFIDENCE_CHECK,
        service.PROMPT_TYPE_SPEAK_RECALL,
    } or source_entry_id is None:
        return None
    audio_assets = await service._load_prompt_audio_assets(
        source_entry_type=source_entry_type,
        source_entry_id=source_entry_id,
        target_id=meaning_id if prompt_type == service.PROMPT_TYPE_AUDIO_TO_DEFINITION else None,
    )
    preferred_accent = await service._get_user_accent_preference(user_id) if user_id is not None else "us"
    return await service._build_prompt_audio_payload(audio_assets, preferred_accent=preferred_accent)


async def build_card_prompt(
    service: "ReviewService",
    *,
    review_mode: str,
    source_text: str,
    definition: str,
    sentence: str | None,
    is_phrase_entry: bool,
    distractor_seed: str,
    meaning_id: uuid.UUID,
    index: int = 0,
    alternative_definitions: list[str] | None = None,
    user_id: uuid.UUID | None = None,
    source_entry_id: uuid.UUID | None = None,
    source_entry_type: str | None = None,
    queue_item_id: uuid.UUID | None = None,
    previous_prompt_type: str | None = None,
    active_target_count: int = 1,
    forced_prompt_type: str | None = None,
    srs_bucket: str | None = None,
    cadence_step: int | None = None,
) -> dict[str, Any]:
    prompt_preferences = await resolve_prompt_preferences(service, user_id)
    available_prompt_types = build_available_prompt_types(
        service,
        review_mode=review_mode,
        sentence=sentence,
        alternative_definitions=alternative_definitions,
        review_depth_preset=prompt_preferences["review_depth_preset"],
        allow_typed_recall=prompt_preferences["allow_typed_recall"],
        allow_audio_spelling=prompt_preferences["allow_audio_spelling"],
        allow_confidence=prompt_preferences["allow_confidence"],
        active_target_count=active_target_count,
        srs_bucket=srs_bucket,
        cadence_step=cadence_step,
    )
    prompt_type = (
        forced_prompt_type
        if forced_prompt_type in service.PROMPT_TYPE_OPTIONS
        else service._select_prompt_type(
            available_prompt_types,
            index=index,
            previous_prompt_type=previous_prompt_type,
        )
    )
    normalized_entry_type = service._normalize_entry_type(
        source_entry_type or ("phrase" if is_phrase_entry else "word")
    )

    audio = await load_prompt_audio_for_type(
        service,
        prompt_type=prompt_type,
        user_id=user_id,
        source_entry_id=source_entry_id,
        source_entry_type=normalized_entry_type,
        meaning_id=meaning_id,
    )
    if prompt_type in {
        service.PROMPT_TYPE_AUDIO_TO_DEFINITION,
        service.PROMPT_TYPE_SPEAK_RECALL,
    } and audio is None:
        fallback_prompt_types = [
            candidate
            for candidate in available_prompt_types
            if candidate != prompt_type
        ]
        fallback_prompt_type = service._select_prompt_type(
            fallback_prompt_types,
            index=index,
            previous_prompt_type=previous_prompt_type,
        )
        if fallback_prompt_type != prompt_type:
            prompt_type = fallback_prompt_type
            audio = await load_prompt_audio_for_type(
                service,
                prompt_type=prompt_type,
                user_id=user_id,
                source_entry_id=source_entry_id,
                source_entry_type=normalized_entry_type,
                meaning_id=meaning_id,
            )

    target_is_word = prompt_type in {
        service.PROMPT_TYPE_DEFINITION_TO_ENTRY,
        service.PROMPT_TYPE_SENTENCE_GAP,
        service.PROMPT_TYPE_COLLOCATION_CHECK,
        service.PROMPT_TYPE_SITUATION_MATCHING,
    }
    resolved_review_mode = service._review_mode_for_prompt_type(prompt_type) or review_mode

    distractors = await load_prompt_distractors(
        service,
        prompt_type=prompt_type,
        user_id=user_id,
        source_entry_id=source_entry_id,
        source_text=source_text,
        definition=definition,
        meaning_id=meaning_id,
        normalized_entry_type=normalized_entry_type,
        is_phrase_entry=is_phrase_entry,
    )

    prompt = await service._build_mandated_prompt(
        review_mode=resolved_review_mode,
        prompt_type=prompt_type,
        word=source_text,
        definition=service._prompt_value_for_options(definition),
        target_is_word=target_is_word,
        distractors=distractors,
        sentence=service._prompt_value_for_options(sentence),
        alternative_definitions=alternative_definitions,
        audio=audio,
    )
    if prompt_type == service.PROMPT_TYPE_SENTENCE_GAP:
        prompt["sentence_masked"] = service._mask_sentence(
            service._prompt_value_for_options(sentence),
            service._prompt_value_for_options(source_text),
        )
    elif prompt_type == service.PROMPT_TYPE_COLLOCATION_CHECK:
        prompt["sentence_masked"] = service._build_collocation_fragment(
            service._prompt_value_for_options(sentence),
            service._prompt_value_for_options(source_text),
        )

    prompt["source_seed"] = service._normalize_prompt_text(distractor_seed) or "review"
    prompt["source_word_id"] = (
        str(source_entry_id)
        if normalized_entry_type == "word" and source_entry_id is not None
        else None
    )
    prompt["source_meaning_id"] = str(meaning_id)
    prompt["source_entry_type"] = normalized_entry_type
    prompt["source_entry_id"] = str(source_entry_id) if source_entry_id is not None else None

    prompt_token = service._encode_prompt_token(
        service._build_prompt_token_payload(
            prompt=prompt,
            user_id=user_id,
            queue_item_id=queue_item_id,
        )
    )
    return service._sanitize_prompt_for_client(prompt=prompt, prompt_token=prompt_token)
