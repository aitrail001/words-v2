from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

REVIEW_SRS_V1_BUCKETS: Final[tuple[str, ...]] = (
    "1d",
    "2d",
    "3d",
    "5d",
    "7d",
    "14d",
    "30d",
    "90d",
    "180d",
    "known",
)

REVIEW_SRS_V1_BUCKET_INTERVAL_DAYS: Final[dict[str, int | None]] = {
    "1d": 1,
    "2d": 2,
    "3d": 3,
    "5d": 5,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
    "180d": 180,
    "known": None,
}

REVIEW_SRS_V1_SCHEDULE_LABELS: Final[dict[str, str]] = {
    "1d": "Tomorrow",
    "2d": "In 2 days",
    "3d": "In 3 days",
    "5d": "In 5 days",
    "7d": "In 1 week",
    "14d": "In 2 weeks",
    "30d": "In 1 month",
    "90d": "In 3 months",
    "180d": "In 6 months",
    "known": "Known",
}

REVIEW_SRS_V1_STAGE_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "stage_1": ("1d", "2d", "3d"),
    "stage_2": ("5d", "7d", "14d"),
    "stage_3": ("30d", "90d", "180d"),
    "known": ("known",),
}

_BUCKET_TO_STAGE_GROUP: Final[dict[str, str]] = {
    "1d": "stage_1",
    "2d": "stage_1",
    "3d": "stage_1",
    "5d": "stage_2",
    "7d": "stage_2",
    "14d": "stage_2",
    "30d": "stage_3",
    "90d": "stage_3",
    "180d": "stage_3",
    "known": "known",
}

_BUCKET_TO_STAGE_STEP: Final[dict[str, int]] = {
    "1d": 0,
    "2d": 1,
    "3d": 2,
    "5d": 0,
    "7d": 1,
    "14d": 2,
    "30d": 0,
    "90d": 1,
    "180d": 2,
    "known": 0,
}

_CADENCE_FAMILIES: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "standard": {
        "stage_1": ("simple",),
        "stage_2": ("simple", "simple", "hard"),
        "stage_3": ("hard", "simple", "hard"),
        "known": ("simple",),
    },
    "deep": {
        "stage_1": ("simple", "simple", "hard"),
        "stage_2": ("hard", "simple", "hard"),
        "stage_3": ("hard", "hard", "simple"),
        "known": ("simple",),
    },
}

REVIEW_SRS_V1_OBJECTIVE_PROMPT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "entry_to_definition",
        "audio_to_definition",
        "definition_to_entry",
        "sentence_gap",
        "typed_recall",
        "speak_recall",
    }
)

_REVIEW_MODE_ALIASES: Final[dict[str, str]] = {
    "gentle": "standard",
    "balanced": "standard",
    "standard": "standard",
    "deep": "deep",
}

_SUCCESS_OUTCOMES: Final[frozenset[str]] = frozenset({"correct_tested", "remember"})
_FAILURE_OUTCOMES: Final[frozenset[str]] = frozenset({"wrong", "lookup"})


def _normalize_bucket(bucket: str) -> str:
    normalized_bucket = (bucket or "").strip()
    if normalized_bucket not in REVIEW_SRS_V1_BUCKETS:
        raise ValueError(f"Unknown SRS bucket: {bucket!r}")
    return normalized_bucket


def normalize_review_mode(review_mode: str | None) -> str:
    normalized_mode = (review_mode or "standard").strip().lower()
    if normalized_mode not in _REVIEW_MODE_ALIASES:
        raise ValueError(f"Unknown review mode: {review_mode!r}")
    return _REVIEW_MODE_ALIASES[normalized_mode]


def bucket_for_interval_days(interval_days: int | float) -> str:
    resolved_interval_days = int(interval_days)
    if resolved_interval_days <= 1:
        return "1d"
    if resolved_interval_days <= 2:
        return "2d"
    if resolved_interval_days <= 3:
        return "3d"
    if resolved_interval_days <= 5:
        return "5d"
    if resolved_interval_days <= 7:
        return "7d"
    if resolved_interval_days <= 14:
        return "14d"
    if resolved_interval_days <= 30:
        return "30d"
    if resolved_interval_days <= 90:
        return "90d"
    return "180d"


def interval_days_for_bucket(bucket: str) -> int | None:
    normalized_bucket = _normalize_bucket(bucket)
    return REVIEW_SRS_V1_BUCKET_INTERVAL_DAYS[normalized_bucket]


def schedule_label_for_bucket(bucket: str) -> str:
    normalized_bucket = _normalize_bucket(bucket)
    return REVIEW_SRS_V1_SCHEDULE_LABELS[normalized_bucket]


def build_schedule_options(default_bucket: str) -> list[dict[str, object]]:
    normalized_bucket = _normalize_bucket(default_bucket)
    return [
        {
            "value": bucket,
            "label": REVIEW_SRS_V1_SCHEDULE_LABELS[bucket],
            "is_default": bucket == normalized_bucket,
        }
        for bucket in REVIEW_SRS_V1_BUCKETS
    ]


def next_due_at_for_bucket(bucket: str, *, now: datetime | None = None) -> datetime | None:
    normalized_bucket = _normalize_bucket(bucket)
    interval_days = REVIEW_SRS_V1_BUCKET_INTERVAL_DAYS[normalized_bucket]
    if interval_days is None:
        return None
    base = now or datetime.now(timezone.utc)
    return base + timedelta(days=interval_days)


def stage_group_for_bucket(bucket: str) -> tuple[str, ...]:
    normalized_bucket = _normalize_bucket(bucket)
    return REVIEW_SRS_V1_STAGE_GROUPS[_BUCKET_TO_STAGE_GROUP[normalized_bucket]]


def cadence_step_for_bucket(bucket: str) -> int:
    normalized_bucket = _normalize_bucket(bucket)
    return _BUCKET_TO_STAGE_STEP[normalized_bucket]


def advance_bucket(bucket: str) -> str:
    normalized_bucket = _normalize_bucket(bucket)
    if normalized_bucket == "known":
        return "known"
    return REVIEW_SRS_V1_BUCKETS[REVIEW_SRS_V1_BUCKETS.index(normalized_bucket) + 1]


def backoff_bucket(bucket: str) -> str:
    normalized_bucket = _normalize_bucket(bucket)
    if normalized_bucket == "1d":
        return "1d"
    if normalized_bucket == "known":
        return "180d"
    return REVIEW_SRS_V1_BUCKETS[REVIEW_SRS_V1_BUCKETS.index(normalized_bucket) - 1]


def select_cadence_family(review_mode: str, bucket: str, cadence_step: int) -> str:
    normalized_mode = normalize_review_mode(review_mode)

    normalized_bucket = _normalize_bucket(bucket)
    stage_group = _BUCKET_TO_STAGE_GROUP[normalized_bucket]
    sequence = _CADENCE_FAMILIES[normalized_mode][stage_group]
    step = int(cadence_step)
    if step < 0 or step > 2:
        raise ValueError(f"Invalid cadence step: {cadence_step!r}")
    return sequence[step % len(sequence)]


def bucket_to_interval_days(bucket: str) -> int:
    interval_days = interval_days_for_bucket(bucket)
    return 180 if interval_days is None else interval_days


def bucket_to_label(bucket: str) -> str:
    return schedule_label_for_bucket(bucket)


def due_at_for_bucket(bucket: str, *, now: datetime | None = None) -> datetime:
    resolved_now = now or datetime.now(timezone.utc)
    return resolved_now + timedelta(days=bucket_to_interval_days(bucket))


def is_success_outcome(outcome: str | None) -> bool:
    return (outcome or "").strip() in _SUCCESS_OUTCOMES


def is_failure_outcome(outcome: str | None) -> bool:
    return (outcome or "").strip() in _FAILURE_OUTCOMES


def next_bucket_after_review(bucket: str, *, prompt_type: str, outcome: str) -> str:
    normalized_bucket = _normalize_bucket(bucket)
    normalized_outcome = (outcome or "").strip()
    if is_success_outcome(normalized_outcome):
        if normalized_bucket == "180d" and not should_graduate_to_known(
            normalized_bucket,
            prompt_type,
            normalized_outcome,
        ):
            return "180d"
        return advance_bucket(normalized_bucket)
    if is_failure_outcome(normalized_outcome):
        return backoff_bucket(normalized_bucket)
    return normalized_bucket


def should_graduate_to_known(bucket: str, prompt_type: str, outcome: str) -> bool:
    return (
        _normalize_bucket(bucket) == "180d"
        and (prompt_type or "").strip() in REVIEW_SRS_V1_OBJECTIVE_PROMPT_TYPES
        and (outcome or "").strip() == "correct_tested"
    )


def resolve_bucket_after_review(bucket: str, prompt_type: str, outcome: str) -> str:
    normalized_bucket = _normalize_bucket(bucket)
    normalized_outcome = (outcome or "").strip()
    if normalized_outcome in {"wrong", "lookup"}:
        return backoff_bucket(normalized_bucket)
    if should_graduate_to_known(normalized_bucket, prompt_type, normalized_outcome):
        return "known"
    if normalized_outcome in {"correct_tested", "remember"}:
        if normalized_bucket == "180d":
            return "180d"
        return advance_bucket(normalized_bucket)
    return normalized_bucket
